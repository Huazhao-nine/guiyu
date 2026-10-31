import AppKit
import Foundation

extension Store {
    func startWorkspaceIndex() {
        guard let workspace = activeWorkspace,hostSandboxed,indexProcess == nil else { return }
        let python = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/GuiyuRuntime/python/bin/python")
        guard FileManager.default.fileExists(atPath:python.path),let resources = Bundle.main.resourceURL else { return }
        let process = Process(),stdin = Pipe(),stdout = Pipe(),epoch = UUID()
        indexEpoch = epoch; indexState = WorkspaceIndexState(); indexBuffer = Data()
        process.executableURL = python
        process.arguments = ["-u",resources.appendingPathComponent("workspace_index.py").path,"--workspace",workspace.path,"--data",dataDir.path,"--embedding",ModelStorage.installed("bge-small-zh-v1.5").path,"--catalog",resources.appendingPathComponent("model-catalog.json").path,"--exclude",baseDataDir.path,"--exclude",ModelStorage.root.path,"--exclude",python.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().path]
        process.currentDirectoryURL = dataDir
        process.environment = ["PATH":"/usr/bin:/bin","LANG":"zh_CN.UTF-8","PYTHONUNBUFFERED":"1","PYTHONDONTWRITEBYTECODE":"1","PYTHONNOUSERSITE":"1","HF_HUB_OFFLINE":"1","DO_NOT_TRACK":"1"]
        process.standardInput = stdin; process.standardOutput = stdout; process.standardError = FileHandle.nullDevice
        process.terminationHandler = { [weak self] _ in DispatchQueue.main.async {
            guard let self,self.indexEpoch == epoch else { return }
            self.indexProcess = nil; self.indexInput = nil; self.indexState.phase = "error"; self.indexState.message = "本地检索已暂停，点击重新建立索引"
            if self.pendingRetrieval != nil { self.completeWorkspaceRetrieval(error:"本地检索已断开，请重新建立索引后再试。") }
        } }
        do {
            try process.run(); indexProcess = process; indexInput = stdin.fileHandleForWriting
            try? stdin.fileHandleForReading.close(); try? stdout.fileHandleForWriting.close()
            let reader = stdout.fileHandleForReading
            DispatchQueue.global(qos:.utility).async { [weak self] in
                defer { try? reader.close() }
                while true {
                    let data = reader.availableData
                    if data.isEmpty { break }
                    DispatchQueue.main.async { if self?.indexEpoch == epoch { self?.consumeIndex(data) } }
                }
            }
            workspaceMonitor = WorkspaceMonitor(path:workspace.path,excluding:[baseDataDir.path,ModelStorage.root.path]) { [weak self] in self?.scheduleIndexUpdate() }
            workspacePoll = Timer.scheduledTimer(withTimeInterval:30,repeats:true) { [weak self] _ in DispatchQueue.main.async { self?.requestIndexSync() } }
        } catch { indexState.phase = "error"; indexState.message = "本地索引暂时无法启动" }
    }
    func stopWorkspaceIndex() {
        indexEpoch = UUID();workspaceMonitor?.stop();workspaceMonitor = nil
        workspacePoll?.invalidate();workspacePoll = nil;workspaceDebounce?.invalidate();workspaceDebounce = nil
        try? indexInput?.close();indexProcess?.terminate();indexProcess = nil;indexInput = nil;indexSyncNeeded = false
        pendingRetrieval = nil;retrievalEvidence = nil;indexState = WorkspaceIndexState()
    }
    func sendIndex(_ request:[String:Any]) {
        guard let indexInput,let data = try? JSONSerialization.data(withJSONObject:request) else { return }
        do { try indexInput.write(contentsOf:data+Data([10])) }
        catch { if pendingRetrieval != nil { completeWorkspaceRetrieval(error:"本地检索暂时断开，请重新建立索引。") } }
    }
    func consumeIndex(_ data:Data) {
        indexBuffer.append(data)
        while let end = indexBuffer.firstIndex(of:10) {
            let line = Data(indexBuffer[..<end]);indexBuffer.removeSubrange(...end)
            guard let value = try? JSONSerialization.jsonObject(with:line) as? [String:Any] else { continue }
            switch value["event"] as? String {
            case "index_privacy": indexNetworkVerified = value["blocked"] as? Bool == true
            case "index_ready":
                if indexUserPaused { indexState.phase = "paused";indexState.message = "本地索引已清空并暂停";indexState.semantic = value["semantic"] as? Bool ?? false }
                else { requestIndexSync() }
            case "index_status":
                indexState = WorkspaceIndexState(value)
                if let inventory = value["inventory"] as? [[String:Any]] {
                    workspaceFiles = inventory.compactMap { item in
                        guard let path = item["path"] as? String,let relative = item["relative"] as? String else { return nil }
                        return WorkspaceFile(path:path,relativePath:relative,bytes:(item["bytes"] as? NSNumber)?.int64Value ?? 0)
                    }
                }
                if indexState.phase == "ready",indexSyncNeeded { indexSyncNeeded = false;requestIndexSync() }
            case "retrieval":
                guard value["request_id"] as? String == pendingRetrieval?["id"] as? String,let result = value["result"] as? [String:Any] else { continue }
                completeWorkspaceRetrieval(result:result)
            case "index_error":
                let message = value["message"] as? String ?? "工作区暂时无法检索"
                if let id = value["request_id"] as? String,id == pendingRetrieval?["id"] as? String { completeWorkspaceRetrieval(error:message) }
                else { indexState.phase = "error";indexState.message = message }
            default:break
            }
        }
    }
    func scheduleIndexUpdate() {
        workspaceDebounce?.invalidate()
        workspaceDebounce = Timer.scheduledTimer(withTimeInterval:0.8,repeats:false) { [weak self] _ in DispatchQueue.main.async { self?.requestIndexSync() } }
    }
    func requestIndexSync(rebuild:Bool = false) {
        guard activeWorkspace != nil else { return }
        if rebuild { indexUserPaused = false;persistScope() }
        guard !indexUserPaused else { return }
        if indexProcess == nil { startWorkspaceIndex();return }
        if indexState.active && indexState.phase != "starting" && !rebuild { indexSyncNeeded = true;return }
        sendIndex(["command":"sync","rebuild":rebuild])
    }
    func clearWorkspaceIndex() {
        guard !contextLocked,!indexState.active else { return }
        indexUserPaused = true;persistScope();sendIndex(["command":"clear"])
        indexState.phase = "paused";indexState.message = "正在清空本地索引并暂停自动更新"
        notice = "索引清空后自动更新会暂停，原文件和工作记录会保留"
    }
    func setWorkspaceAutomatic(_ enabled:Bool) {
        guard !contextLocked else { return }
        let previousPage = page;newTask();page = previousPage;workspaceAutomatic = enabled;retrievalEvidence = nil
        if enabled { selectedPaths = [];documents = [] }
        persistScope()
    }
    func requestWorkspaceRetrieval(_ payload:[String:Any],reusePrevious:Bool = false) {
        pendingRetrieval = payload
        guard !indexUserPaused else { completeWorkspaceRetrieval(error:"本地索引已清空并暂停。请在“我的资料”重新建立索引，或改为手动选择。");return }
        if indexProcess == nil { startWorkspaceIndex() }
        guard indexProcess != nil else { completeWorkspaceRetrieval(error:"本地索引尚未就绪，请先建立索引。") ;return }
        var request:[String:Any] = ["command":"retrieve","request_id":payload["id"]!,"query":payload["prompt"]!,"kind":payload["kind"] ?? "auto"]
        if let current = planningParentForRetrieval,let plan = current.plan,plan.state == "completed" {
            // Read only this task's immutable, local plan metadata; no whole-thread factual text enters retrieval.
            let path = dataDir.appendingPathComponent("Plans/"+plan.id+".json")
            if let data = try? Data(contentsOf:path),let saved = try? JSONSerialization.jsonObject(with:data) as? [String:Any],let snapshots = saved["snapshot"] as? [String:String] {
                request["previous"] = ["snapshots":snapshots,"retrieval":saved["retrieval"] as? [String:Any] ?? ["query":saved["prompt"] as? String ?? ""]]
                request["continue_previous"] = reusePrevious
            }
        }
        sendIndex(request)
    }
}
