import AppKit
import Combine
import Foundation
import UniformTypeIdentifiers

@MainActor
final class Store: ObservableObject {
    @Published var page: Page = .workspace
    @Published var prompt = ""
    @Published var kind: TaskKind = .auto
    @Published var documents: [SourceDoc] = []
    @Published var selectedPaths: [String] = []
    @Published var ready = false
    @Published var networkVerified = false
    @Published var isBusy = false
    @Published var isPlanning = false
    @Published var intelligentExecution = true
    @Published var agentPlan: AgentPlan?
    @Published var isInspecting = false
    @Published var isApplying = false
    @Published var bootMessage = "正在准备你的本地空间"
    @Published var step = 0
    @Published var progressDetail = ""
    @Published var responseMode = ""
    @Published var liveToolCalls:[LocalToolCall] = []
    @Published var streamed = ""
    @Published var activePrompt = ""
    @Published var current: TaskRecord?
    // A restored or saved response owns its trace, including an empty legacy
    // trace. Failed in-flight calls must not appear on that earlier response.
    var displayedToolCalls: [LocalToolCall] {
        if let record = current { return record.toolCalls ?? [] }
        return liveToolCalls
    }
    @Published var history: [TaskRecord] = []
    @Published var notice: String?
    @Published var errorMessage: String?
    @Published var previewArtifact: Artifact?
    @Published var previewSource: SourceDoc?
    @Published var showWelcome = false
    @Published var showClearConfirmation = false
    @Published var skippedMessages: [String] = []
    @Published var elapsed: Double = 0
    @Published var activeThreadID: String?
    @Published var showQueryBuilder = false
    @Published var schemaLoading = false
    @Published var schemaColumns: [String] = []
    @Published var schemaNumericColumns: [String] = []
    @Published var schemaValues: [String:[String]] = [:]
    @Published var schemaRowCount = 0
    @Published var schemaQuery = TableQuery()
    @Published var showModelLibrary = false
    @Published var localModels: [LocalModelOption] = []
    @Published var selectedModelID = PrimaryModel.id
    @Published var loadedModelName = ""
    @Published var lastWorkingModelID: String?
    @Published var workspaceAutomatic = true
    @Published var indexUserPaused = false
    @Published var indexState = WorkspaceIndexState()
    @Published var indexNetworkVerified = false
    @Published var retrievalEvidence:RetrievalEvidence?
    var indexProcess:Process?
    var indexInput:FileHandle?
    var indexBuffer = Data()
    var indexEpoch = UUID()
    var pendingRetrieval:[String:Any]?
    var pendingRouting:[String:Any]?
    private var planningSourceParent:TaskRecord?
    var indexSyncNeeded = false
    var workspaceMonitor:WorkspaceMonitor?
    var workspacePoll:Timer?
    var workspaceDebounce:Timer?
    var planningParentForRetrieval:TaskRecord? { planningSourceParent }
    private var nextQuery: [String:Any]?
    private var directReply = false
    private var automaticPlanGate=AutomaticPlanGate()
    private var planningParent: TaskRecord?
    var selectedModel: LocalModelOption? { localModels.first { $0.id == selectedModelID } }
    var threadRecords: [TaskRecord] {
        guard let anchor = current ?? planningParent, (anchor.threadID ?? anchor.id) == activeThreadID else { return [] }
        var records: [TaskRecord] = [], cursor: TaskRecord? = anchor, seen = Set<String>()
        while let record = cursor, !seen.contains(record.id), records.count < 60 {
            records.append(record); seen.insert(record.id)
            cursor = record.parentID.flatMap { parent in history.first { $0.id == parent } }
        }
        return records.reversed()
    }
    var previousTurns: [TaskRecord] { threadRecords.filter { $0.id != current?.id } }

    let root: URL
    let baseDataDir: URL
    var dataDir: URL { activeWorkspaceID.map { baseDataDir.appendingPathComponent("Workspaces/"+$0,isDirectory:true) } ?? baseDataDir }
    @Published var workspaces: [LocalWorkspace] = []
    @Published var activeWorkspaceID: String?
    @Published var workspaceFiles: [WorkspaceFile] = []
    @Published var workspaceScanning = false
    @Published var workspaceScanMessage: String?
    @Published var showWorkspacePicker = false
    @Published var showPreferences = false
    @Published var preferences = PersonalPreferences()
    @Published var modelCatalog: [CatalogModel] = CatalogModel.load()
    @Published var downloadStatuses: [String:ModelDownloadStatus] = [:]
    private var downloadTimer: Timer?
    private var runtimeDir: URL { FileManager.default.urls(for:.applicationSupportDirectory,in:.userDomainMask)[0].appendingPathComponent("GuiyuRuntime") }
    let hostSandboxed: Bool
    private var worker: Process?
    private var input: FileHandle?
    private var buffer = Data()
    private var started: Date?
    private var timer: Timer?
    private var currentID = ""
    private var workerEpoch = UUID()
    private var restoringPlanID: String?
    private var processingActivity: NSObjectProtocol?
    private var pendingPlanURL: URL { dataDir.appendingPathComponent("pending-plan.json") }

    init(root: URL, hostSandboxed: Bool) {
        self.root = root
        self.hostSandboxed = hostSandboxed
        baseDataDir = ProcessInfo.processInfo.environment["GUIYU_DATA_DIR"].map { URL(fileURLWithPath:$0,isDirectory:true) } ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Guiyu", isDirectory: true)
        try? FileManager.default.createDirectory(at:baseDataDir,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        if let data = try? Data(contentsOf:baseDataDir.appendingPathComponent("preferences.json")),let saved = try? JSONDecoder().decode(PersonalPreferences.self,from:data) { preferences = saved }
        if let data = try? Data(contentsOf:baseDataDir.appendingPathComponent("workspaces.json")),let registry = try? JSONDecoder().decode(WorkspaceRegistry.self,from:data) {
            workspaces = registry.workspaces.filter { UUID(uuidString:$0.id) != nil }
            if workspaces.contains(where:{$0.id == registry.selectedID}) { activeWorkspaceID = registry.selectedID }
        }
        loadWorkspaceState()
        let defaultModel = modelCatalog.first(where:{$0.id == PrimaryModel.id}).flatMap { PrimaryModel.prepared($0) } ?? PrimaryModel.placeholder()
        localModels = [defaultModel]
        if let data = try? Data(contentsOf:baseDataDir.appendingPathComponent("local-models.json")), let library = try? JSONDecoder().decode(ModelLibrary.self,from:data) {
            for model in library.models where model.id != PrimaryModel.id && model.bytes>0 && FileManager.default.fileExists(atPath:URL(fileURLWithPath:model.path).appendingPathComponent("config.json").path) {
                if !localModels.contains(where:{$0.id==model.id || $0.path==model.path}) { localModels.append(model) }
            }
            if localModels.contains(where:{$0.id == library.selectedID}) { selectedModelID = library.selectedID }
        }
        showWelcome = !FileManager.default.fileExists(atPath: baseDataDir.appendingPathComponent("welcomed").path)
        refreshModelDownloads()
        let dailyMarker=baseDataDir.appendingPathComponent("primary-32gb-v0.25")
        if !FileManager.default.fileExists(atPath:dailyMarker.path) {
            selectedModelID=PrimaryModel.id;persistModels()
            notice="已选择 Qwen3.6 35B A3B，适合 32 GB 设备"
            try? Data(PrimaryModel.id.utf8).write(to:dailyMarker,options:.atomic)
        }
        downloadTimer = Timer.scheduledTimer(withTimeInterval:0.5,repeats:true) { [weak self] _ in DispatchQueue.main.async { self?.refreshModelDownloads() } }
        if activeWorkspace != nil { refreshWorkspace() }
        startWorker()
    }

    func resetContext() {
        retrievalEvidence = nil; current = nil; planningParent = nil; planningSourceParent = nil; pendingRouting = nil; activeThreadID = nil; agentPlan = nil; nextQuery = nil; directReply = false
        activePrompt = ""; streamed = ""; prompt = ""; kind = .auto; responseMode = ""; liveToolCalls = []; errorMessage = nil; notice = nil
        restoringPlanID = nil; schemaColumns = []; schemaNumericColumns = []; schemaValues = [:]; schemaQuery = TableQuery(); schemaRowCount = 0; schemaLoading = false
        skippedMessages = []; showQueryBuilder = false; previewSource = nil; previewArtifact = nil
    }

    func startWorker() {
        guard worker == nil || worker?.isRunning == false else { return }
        ready = false
        networkVerified = false
        if activeWorkspace != nil { startWorkspaceIndex() }
        guard hostSandboxed else { bootMessage = "本地隔离没有生效"; errorMessage = "归屿没有读取资料。请使用项目提供的应用重新启动。"; return }
        let runtime = runtimeDir
        let python = runtime.appendingPathComponent("python/bin/python")
        let model = URL(fileURLWithPath:selectedModel?.path ?? ModelStorage.installed(PrimaryModel.id).path)
        guard FileManager.default.fileExists(atPath: python.path), FileManager.default.fileExists(atPath: model.appendingPathComponent("config.json").path) else {
            bootMessage = "还差一步，准备本地模型"
            errorMessage = "打开本地模型库，下载并选择一个模型。首次使用仍需用「准备归屿.command」安装运行环境。"
            return
        }
        if let selectedModel, !DevicePolicy.allows(selectedModel) {
            bootMessage="请选择适合当前内存的模型"
            errorMessage="当前默认模型需要至少 32 GB 内存。请在 32 GB 或更大内存的 Apple 芯片 Mac 上使用。";return
        }
        let process = Process(), stdin = Pipe(), stdout = Pipe()
        let epoch = UUID()
        workerEpoch = epoch
        process.executableURL = python
        process.arguments = ["-u", Bundle.main.resourceURL!.appendingPathComponent("worker.py").path, "--model", model.path, "--model-name", selectedModel?.name ?? "本地模型", "--data", dataDir.path]
        process.environment = ["PATH": "/usr/bin:/bin", "LANG": "zh_CN.UTF-8", "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1", "TOKENIZERS_PARALLELISM": "false"]
        process.currentDirectoryURL = dataDir
        process.standardInput = stdin
        process.standardOutput = stdout
        process.standardError = FileHandle.nullDevice
        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self else { return }
                guard self.workerEpoch == epoch else { return }
                self.ready = false
                self.isBusy = false
                self.isPlanning = false
                self.isInspecting = false
                self.isApplying = false
                self.timer?.invalidate()
                self.endProcessingActivity()
                self.bootMessage = "本地引擎已暂停"
            }
        }
        do {
            buffer.removeAll()
            beginProcessingActivity()
            try process.run()
            worker = process
            input = stdin.fileHandleForWriting
            bootMessage = "正在唤醒本地模型"
            let reader = stdout.fileHandleForReading
            // Drain the pipe on a dedicated reader, including events already buffered at startup.
            // Keep blocking I/O off the main actor and discard events from terminated workers.
            try? stdout.fileHandleForWriting.close()
            try? stdin.fileHandleForReading.close()
            DispatchQueue.global(qos:.userInitiated).async { [weak self] in
                defer { try? reader.close() }
                while true {
                    let data = reader.availableData
                    if data.isEmpty { break }
                    DispatchQueue.main.async { if self?.workerEpoch == epoch { self?.consume(data) } }
                }
            }
        } catch { endProcessingActivity(); errorMessage = "本地引擎未能启动，请检查准备工具是否完成。" }
    }

    private func consume(_ data: Data) {
        buffer.append(data)
        while let newline = buffer.firstIndex(of: 10) {
            let line = buffer[..<newline]
            buffer.removeSubrange(...newline)
            if let event = try? JSONSerialization.jsonObject(with: Data(line)) as? [String: Any] { handle(event) }
        }
    }

    private func handle(_ event: [String: Any]) {
        switch event["event"] as? String {
        case "privacy": networkVerified = event["blocked"] as? Bool == true
        case "boot": bootMessage = event["detail"] as? String ?? "正在准备"
        case "ready":
            endProcessingActivity()
            ready = networkVerified
            loadedModelName = selectedModel?.name ?? "本地模型"
            lastWorkingModelID = selectedModelID
            bootMessage = ready ? "本地模型已就绪" : "隔离尚未确认"
            if let plan = agentPlan, plan.state != "completed" {
                restoringPlanID = plan.id
                send(["command":"get_plan","plan_id":plan.id])
            }
            if !selectedPaths.isEmpty && !workspaceScanning { inspect() }
        case "documents", "sources":
            documents = (event["documents"] as? [[String: Any]] ?? []).map(SourceDoc.init)
            skippedMessages = (event["skipped"] as? [[String: Any]] ?? []).map { "\($0["name"] as? String ?? "资料")：\($0["reason"] as? String ?? "暂未读取")" }
            isInspecting = false
            if event["event"] as? String == "documents" {
                notice = documents.isEmpty ? "所选位置没有可读取的资料" : "已添加 \(documents.count) 份资料，仅在本机读取"
            }
        case "progress": step = event["step"] as? Int ?? 0; progressDetail = event["detail"] as? String ?? ""
        case "route":
            guard let requestID = event["request_id"] as? String, requestID == pendingRouting?["id"] as? String,
                  let decision = event["decision"] as? [String:Any] else { return }
            completeTaskRouting(decision)
        case "delta": streamed += event["text"] as? String ?? ""
        case "tool_call":
            if let object = event["call"] as? [String:Any] {
                let call = LocalToolCall(object)
                if let i = liveToolCalls.firstIndex(where:{$0.id == call.id}) { liveToolCalls[i] = call }
                else { liveToolCalls.append(call) }
                progressDetail = call.state == "running" ? "正在本机" + call.title : "已完成本地核对，正在组织结果"
            }
        case "plan":
            if let object = event["plan"] as? [String:Any] {
                var incoming = AgentPlan(object)
                // The pending cache can contain edits made after the last worker checkpoint.
                if restoringPlanID == incoming.id, let cached = agentPlan, cached.id == incoming.id {
                    for index in incoming.steps.indices where incoming.steps[index].state != "completed" {
                        if let edit = cached.steps.first(where: { $0.id == incoming.steps[index].id }) {
                            incoming.steps[index].instruction = edit.instruction
                            incoming.steps[index].enabled = edit.enabled
                        }
                    }
                    restoringPlanID = nil
                }
                agentPlan = incoming
                if let evidence = incoming.retrieval { retrievalEvidence = evidence }
                activeThreadID = incoming.threadID ?? incoming.id
                if let sources = object["sources"] as? [[String:Any]], !sources.isEmpty { documents = sources.map(SourceDoc.init) }
                persistPendingPlan()
                if agentPlan?.state == "draft" {
                    let automatic=automaticPlanGate.consume(incoming,requestID:event["request_id"] as? String)
                    finishTask();notice=automatic ? nil : "已拟好步骤，你可以调整后开始"
                    if automatic { directReply=false;executePlan() }
                }
            }
        case "checkpoint", "complete":
            if let result = event["result"] as? [String: Any] {
                let record = TaskRecord(result, sourceCache: documents)
                current = record
                activeThreadID = record.threadID ?? record.id
                if let i = history.firstIndex(where:{$0.id == record.id}) { history[i] = record }
                else { history.insert(record, at: 0) }
                history = Array(history.prefix(60))
                persistHistory()
            }
            if event["event"] as? String == "complete" { finishTask(); persistPendingPlan() }
        case "transaction":
            if let object = event["transaction"] as? [String: Any] {
                let tx = FileTransaction(object)
                for move in tx.moves {
                    let oldPath = tx.state == "undone" ? move.destination : move.source
                    let newPath = tx.state == "undone" ? move.source : move.destination
                    if let i = selectedPaths.firstIndex(of: oldPath) { selectedPaths[i] = newPath }
                }
                current?.transaction = tx
                if let index = history.firstIndex(where: { $0.transaction?.id == tx.id }) { history[index].transaction = tx }
                persistHistory()
                notice = tx.state == "undone" ? "本次整理已撤销，文件回到原位置" : "整理完成，仍可撤销本次修改"
            }
            isApplying = false
            persistScope()
            if activeWorkspace != nil { refreshWorkspace() } else if ready { inspect() }
        case "schema":
            schemaColumns = event["columns"] as? [String] ?? []
            schemaNumericColumns = event["numeric_columns"] as? [String] ?? []
            schemaValues = event["values"] as? [String:[String]] ?? [:]
            schemaRowCount = event["row_count"] as? Int ?? 0
            schemaQuery = TableQuery(event["query"] as? [String:Any] ?? [:]); schemaLoading = false
        case "fatal":
            errorMessage = event["message"] as? String
            ready = false
            bootMessage = "本地引擎需要重新准备"
            finishTask()
        case "error":
            pendingRouting = nil; pendingRetrieval = nil
            errorMessage = event["message"] as? String
            if isPlanning {
                prompt = activePrompt
                if let parent = planningParent { current = parent; agentPlan = parent.plan; activePrompt = parent.prompt }
            }
            isInspecting = false; isApplying = false; schemaLoading = false; finishTask()
        case "awaiting_input":
            notice = "已保留当前结果，补充要求后可以继续"
            finishTask()
        default: break
        }
    }

    var privacyRequest:[String:Any] {
        let settings=UserDefaults.standard
        let selected=settings.string(forKey:"guiyu.privacy.detector") ?? "rules"
        let detector=["astrlink-guard","openai-privacy-filter"].contains(selected) ? selected : "astrlink-guard"
        func flag(_ key:String,_ fallback:Bool)->Bool { settings.object(forKey:key)==nil ? fallback : settings.bool(forKey:key) }
        return ["detector":detector,"policy":["secrets":flag("guiyu.privacy.secrets",true),"personal":flag("guiyu.privacy.contacts",true),"categories":["person":flag("guiyu.privacy.names",true),"address":flag("guiyu.privacy.addresses",true),"date":flag("guiyu.privacy.dates",false),"account":flag("guiyu.privacy.accounts",true),"identity":flag("guiyu.privacy.accounts",true),"bank":flag("guiyu.privacy.accounts",true),"ip":flag("guiyu.privacy.network",false),"url":flag("guiyu.privacy.network",false)]]]
    }

    private func send(_ object: [String: Any]) {
        var payload = object
        let command = payload["command"] as? String ?? ""
        if command == "plan" { payload["privacy"]=privacyRequest;payload["preferences"] = preferences.object;payload["adaptive"] = intelligentExecution;payload["workbook_mode"]="flow" }
        if ["chat","assist"].contains(command) { payload["preferences"] = preferences.object }
        if !["route","chat","assist"].contains(command), payload["source_free"] as? Bool != true, let workspace = activeWorkspace { payload["workspace_root"] = workspace.path }
        guard let input, let data = try? JSONSerialization.data(withJSONObject: payload) else { return }
        do { try input.write(contentsOf: data + Data([10])) }
        catch { errorMessage = "本地引擎暂时断开，请重新连接。"; finishTask() }
    }

    func runTask() {
        let request = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard ready, !contextLocked, !request.isEmpty else { return }
        beginProcessingActivity()
        errorMessage = nil; notice = nil; currentID = UUID().uuidString
        planningParent = current
        let allRecords = threadRecords.isEmpty ? (current.map { [$0] } ?? []) : threadRecords
        let contextRecords = Array(allRecords.suffix(6))
        planningSourceParent = allRecords.last { $0.plan?.state == "completed" && $0.plan?.paths.isEmpty == false }
        let conversation: [[String:String]] = contextRecords.flatMap { [["role":"user","text":String($0.prompt.prefix(1500))],["role":"assistant","text":String($0.text.prefix(2500))]] }
        let planned = kind.usesPlan
        directReply = kind == .answer
        automaticPlanGate.arm(id:currentID,prompt:request)
        activePrompt = request; streamed = ""; current = nil; agentPlan = nil; retrievalEvidence = nil; liveToolCalls = []; responseMode = "routing"; isBusy = true; isPlanning = planned; step = 0; elapsed = 0; started = Date(); page = .workspace
        persistPendingPlan()
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in
            DispatchQueue.main.async { if let self, let started = self.started { self.elapsed = Date().timeIntervalSince(started) } }
        }
        var payload: [String:Any] = ["id":currentID,"command":planned ? "plan" : "run","prompt":request,"kind":kind.rawValue,"paths":selectedPaths,"history":conversation]
        if let parent = planningParent { payload["conversation_parent_id"] = parent.id; payload["thread_id"] = parent.threadID ?? parent.id }
        if let parent = planningSourceParent { payload["parent_id"] = parent.id }
        if let nextQuery { payload["query"] = nextQuery }; nextQuery = nil
        pendingRouting = payload; isPlanning = true; progressDetail = "正在理解你的目标，判断是否需要资料或工具"
        var routing:[String:Any] = ["command":"route","id":currentID,"prompt":request,"kind":kind.rawValue,"history":conversation,"workspace_available":activeWorkspace != nil,"files_selected":!selectedPaths.isEmpty]
        if let parent = planningSourceParent { routing["previous_source"] = ["prompt":String(parent.prompt.prefix(1000)),"query":parent.querySummary ?? "","source_names":parent.plan?.sourceNames ?? parent.sources.map(\.name)] }
        if let query = payload["query"] { routing["query"] = query }
        if kind == .auto && WorkbookFollowupIntent.requiresSource(request,parent:planningSourceParent) {
            completeTaskRouting(["mode":"workspace","use_previous":true,"source":"explicit_workbook_followup"])
        } else { send(routing) }
        prompt = ""; kind = .auto
    }

    func completeTaskRouting(_ decision:[String:Any]) {
        guard var payload = pendingRouting else { return }
        pendingRouting = nil
        responseMode = decision["mode"] as? String ?? ""
        switch decision["mode"] as? String {
        case "chat", "clarify", "tools":
            payload["command"] = responseMode == "tools" ? "assist" : "chat"; payload["paths"] = []; payload.removeValue(forKey:"parent_id"); payload.removeValue(forKey:"query")
            payload["clarification"] = decision["mode"] as? String == "clarify"
            isPlanning = false; directReply = false; progressDetail = responseMode == "tools" ? "正在选择本地计算与日期工具" : "正在本机思考与回答，无需读取资料"
            send(payload)
        case "task":
            payload["command"] = "plan"; payload["source_free"] = true; payload["paths"] = []; payload.removeValue(forKey:"parent_id"); payload.removeValue(forKey:"query")
            isPlanning = true; progressDetail = "正在按你的目标安排写作与规划"
            send(payload)
        case "workspace":
            payload["source_required"] = true
            if decision["use_previous"] as? Bool != true { payload.removeValue(forKey:"parent_id"); planningSourceParent = nil }
            if decision["source"] as? String == "share_contract", !selectedPaths.isEmpty,
               activePrompt.range(of:"这份|这些|当前|刚才|上面",options:.regularExpression) != nil {
                payload["paths"]=selectedPaths;payload["command"]="plan";isPlanning=true;send(payload)
            } else if activeWorkspace != nil && workspaceAutomatic {
                progressDetail = "需要资料，正在从工作区查找"; requestWorkspaceRetrieval(payload,reusePrevious:decision["use_previous"] as? Bool == true)
            } else if selectedPaths.isEmpty {
                errorMessage = "这项任务需要你的资料。添加文件或选择工作区后，我就能继续。"; prompt = activePrompt
                if let parent = planningParent { current = parent; agentPlan = parent.plan; activePrompt = parent.prompt }
                finishTask()
            } else { payload["command"] = "plan"; isPlanning = true; send(payload) }
        default:
            errorMessage = "未能确定任务方式，请重新描述你的目标。"; prompt = activePrompt
            if let parent = planningParent { current = parent; agentPlan = parent.plan; activePrompt = parent.prompt }
            finishTask()
        }
    }

    func completeWorkspaceRetrieval(result:[String:Any]? = nil,error:String? = nil) {
        guard var payload = pendingRetrieval else { return }
        pendingRetrieval = nil
        if let error {
            errorMessage = error; prompt = payload["prompt"] as? String ?? ""
            if let parent = planningParent { current = parent;agentPlan = parent.plan;activePrompt = parent.prompt }
            finishTask();return
        }
        guard let result,let paths = result["paths"] as? [String],!paths.isEmpty else {
            errorMessage = "工作区没有找到足够相关的资料。可以换个说法，或在“我的资料”限定范围。";prompt = payload["prompt"] as? String ?? ""
            if let parent = planningParent { current = parent;agentPlan = parent.plan;activePrompt = parent.prompt }
            finishTask();return
        }
        selectedPaths = paths;documents = [];persistScope();retrievalEvidence = RetrievalEvidence(result)
        var evidence = result;evidence.removeValue(forKey:"status")
        payload["paths"] = paths;payload["retrieval"] = evidence
        if result["refreshed"] as? Bool == true { payload["refresh_sources"] = true }
        else if result["reuse"] as? Bool != true {
            payload.removeValue(forKey:"parent_id")
            // A new source scope must not treat old assistant prose as factual evidence.
            payload["history"] = (payload["history"] as? [[String:String]] ?? []).filter { $0["role"] == "user" }
        }
        // Workspace tasks always use the reviewed plan so retrieval evidence and snapshots persist.
        payload["command"] = "plan";isPlanning = true
        send(payload)
    }

    private func beginProcessingActivity() {
        if processingActivity == nil {
            processingActivity = ProcessInfo.processInfo.beginActivity(options:.userInitiatedAllowingIdleSystemSleep,reason:"归屿正在准备或处理本地任务")
        }
    }
    private func endProcessingActivity() {
        if let activity = processingActivity { ProcessInfo.processInfo.endActivity(activity); processingActivity = nil }
    }
    private func finishTask() { isBusy = false; isPlanning = false; timer?.invalidate(); timer = nil; started = nil; endProcessingActivity() }

    func persistPendingPlan() {
        if let plan = agentPlan, plan.state != "completed", let data = try? JSONEncoder().encode(plan) {
            try? data.write(to:pendingPlanURL,options:.atomic)
            try? FileManager.default.setAttributes([.posixPermissions:0o600],ofItemAtPath:pendingPlanURL.path)
        } else { try? FileManager.default.removeItem(at:pendingPlanURL) }
    }

    func updatePlanStep(_ id: String,instruction: String? = nil,enabled: Bool? = nil) {
        guard var plan = agentPlan, plan.canContinue, let index = plan.steps.firstIndex(where:{$0.id == id}), plan.steps[index].state != "completed" else { return }
        if let instruction { plan.steps[index].instruction = instruction }
        if let enabled { plan.steps[index].enabled = enabled }
        agentPlan = plan; persistPendingPlan()
    }

    func executePlan() {
        guard let plan = agentPlan, plan.canContinue, plan.enabledCount > 0, ready, !isBusy, !isInspecting else { return }
        beginProcessingActivity()
        selectedPaths = plan.paths
        errorMessage = nil; notice = nil; streamed = ""; isBusy = true; isPlanning = false; elapsed = 0; started = Date()
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval:0.2,repeats:true) { [weak self] _ in
            DispatchQueue.main.async { if let self, let started = self.started { self.elapsed = Date().timeIntervalSince(started) } }
        }
        let edits: [[String:Any]] = plan.steps.map { ["id":$0.id,"enabled":$0.enabled,"instruction":$0.instruction] }
        send(["command":"execute_plan","plan_id":plan.id,"steps":edits,"paths":plan.paths])
    }

    func cancelTask() {
        guard !isApplying else { return }
        automaticPlanGate.clear()
        pendingRetrieval = nil; pendingRouting = nil
        ready = false; networkVerified = false; bootMessage = "正在恢复本地引擎"
        workerEpoch = UUID()
        try? input?.close()
        worker?.terminate()
        worker = nil; input = nil
        finishTask(); isInspecting = false; streamed = "任务已停止，未生成新的结果。"
        if var plan = agentPlan {
            plan.state = "paused"
            for i in plan.steps.indices where plan.steps[i].state == "running" { plan.steps[i].state = "pending" }
            agentPlan = plan; current?.plan = plan
            if let i = history.firstIndex(where:{$0.id == plan.id}) { history[i].plan = plan; persistHistory() }
            persistPendingPlan(); streamed = ""
        }
        notice = "已停止，正在恢复本地空间"
        DispatchQueue.main.asyncAfter(deadline: .now()+0.7) { self.startWorker() }
    }

    func shutdown() {
        stopWorkspaceIndex()
        endProcessingActivity()
        workerEpoch = UUID()
        timer?.invalidate()
        try? input?.close()
        worker?.terminate()
        worker = nil; input = nil
    }

    func chooseFiles(folder: Bool = false) {
        guard !contextLocked else { return }
        if activeWorkspace != nil { page = .library; return }
        let panel = NSOpenPanel()
        panel.title = folder ? "选择归屿可以读取的文件夹" : "选择本次使用的资料"
        panel.prompt = "添加资料"
        panel.message = "仅在这台电脑上读取。支持文本、PDF、Word 和 Excel。"
        panel.canChooseDirectories = folder; panel.canChooseFiles = !folder; panel.allowsMultipleSelection = !folder
        if !folder { panel.allowedContentTypes = [UTType(filenameExtension:"txt"), UTType(filenameExtension:"md"), .pdf, UTType(filenameExtension:"docx"), UTType(filenameExtension:"xlsx"), .commaSeparatedText].compactMap { $0 } }
        panel.begin { [weak self] response in
            guard response == .OK else { return }
            DispatchQueue.main.async { self?.addPaths(panel.urls.map(\.path)) }
        }
    }

    func addPaths(_ paths: [String]) {
        guard !isBusy, !isInspecting else { return }
        if let workspace = activeWorkspace {
            guard paths.allSatisfy({ WorkspaceScanner.contains($0,in:workspace.path) && WorkspaceScanner.extensions.contains(URL(fileURLWithPath:$0).pathExtension.lowercased()) }) else { errorMessage = "请在工作区的资料列表中勾选文档。其他文件可先切换到个人空间再添加。"; return }
            setWorkspaceSelection(selectedPaths+paths); return
        }
        selectedPaths = Array(Set(selectedPaths + paths)).sorted()
        persistScope()
        current = nil; activeThreadID = nil; agentPlan = nil; persistPendingPlan(); activePrompt = ""; streamed = ""
        if ready { inspect() }
    }

    func inspect() { guard ready, !isBusy else { return }; isInspecting = true; send(["command":"inspect","paths":selectedPaths]) }

    func removeSources() {
        guard !isBusy else { return }
        if activeWorkspace != nil { workspaceAutomatic = false }
        selectedPaths = []; documents = []; current = nil; activeThreadID = nil; agentPlan = nil; persistPendingPlan(); activePrompt = ""; skippedMessages = []
        persistScope(); notice = "已取消本次资料授权，原文件未改动"
    }

    func useDemo(office: Bool = false, query: Bool = false) {
        guard !contextLocked else { return }
        if activeWorkspace != nil { switchWorkspace(nil) }
        let source = Bundle.main.resourceURL!.appendingPathComponent(query ? "query" : office ? "office" : "demo")
        let destination = dataDir.appendingPathComponent("Examples/\(UUID().uuidString)")
        do {
            try FileManager.default.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
            try FileManager.default.copyItem(at: source, to: destination)
            selectedPaths = [destination.path]
            page = .workspace; current = nil; activeThreadID = nil; agentPlan = nil; persistPendingPlan(); activePrompt = ""; streamed = ""
            kind = query ? .statistics : office ? .workflow : .table
            prompt = query ? "只统计状态包含待报销且金额大于100元，按经办人分组统计。" : kind.prompt
            persistScope()
            if ready { inspect() }
            notice = "已加入虚构示例资料，可放心体验整理与撤销"
        } catch { errorMessage = "示例资料暂时无法打开，请重新准备应用。" }
    }

    func chooseTemplate(_ value: TaskKind) { kind = value; prompt = value.prompt; page = .workspace }
    func newTask() { guard !isBusy else { return }; automaticPlanGate.clear(); retrievalEvidence = nil; current = nil; planningParent = nil; planningSourceParent = nil; pendingRouting = nil; responseMode = ""; liveToolCalls = []; activeThreadID = nil; agentPlan = nil; nextQuery = nil; persistPendingPlan(); activePrompt = ""; streamed = ""; prompt = ""; kind = .auto; page = .workspace }
    func openRecord(_ record: TaskRecord) {
        guard !contextLocked else { return }; automaticPlanGate.clear(); errorMessage = nil; notice = nil; current = record; liveToolCalls = []; activeThreadID = record.threadID ?? record.id; agentPlan = record.plan; retrievalEvidence = record.plan?.retrieval; activePrompt = record.prompt; streamed = ""; page = .workspace
        selectedPaths = record.plan?.paths ?? record.sources.map(\.path); documents = record.sources; persistScope()
        if ready && !selectedPaths.isEmpty { inspect() }
    }

    func followUp(_ value: String) { guard !isBusy else { return }; kind = .auto; prompt = value; runTask() }
    func supplementGoal() {
        guard !isBusy,let plan = agentPlan else { return }
        kind = .auto;prompt = plan.prompt+"\n\n补充要求：";page = .workspace
        notice = "补充信息后，归屿会重新安排这项目标"
    }
    func openFilters() {
        guard ready, !isBusy, !isInspecting else { return }
        errorMessage = nil; schemaLoading = true; schemaColumns = []; showQueryBuilder = true
        var request: [String:Any] = ["command":"schema","paths":selectedPaths]
        if current?.plan?.state == "completed", let id = current?.id { request["parent_id"] = id }
        send(request)
    }
    func applyFilters(_ query: TableQuery) {
        nextQuery = query.object; showQueryBuilder = false; kind = .statistics
        prompt = "按面板设置的条件筛选并统计，保留匹配的数据。"; runTask()
    }
    func useSearchHits(_ hits: [SearchHit]) {
        guard !isBusy else { return }; if activeWorkspace != nil { setWorkspaceSelection(hits.map(\.path)); return }; newTask(); selectedPaths = hits.map(\.path); if ready { inspect() }
        notice = "本次范围已改为 \(hits.count) 份匹配资料"
    }

    func persistModels() {
        let library = ModelLibrary(selectedID:selectedModelID,models:localModels)
        let url = baseDataDir.appendingPathComponent("local-models.json")
        if let data = try? JSONEncoder().encode(library) { try? data.write(to:url,options:.atomic); try? FileManager.default.setAttributes([.posixPermissions:0o600],ofItemAtPath:url.path) }
    }
    func addLocalModel() {
        guard !isBusy else { return }
        let panel = NSOpenPanel(); panel.title = "添加本地 MLX 模型"; panel.prompt = "添加到模型库"; panel.canChooseDirectories = true; panel.canChooseFiles = false
        panel.message = "选择已准备好的 MLX 模型文件夹，权重保留在原位置。添加后可选择切换。"
        panel.begin { [weak self] response in
            guard response == .OK, let url = panel.url else { return }
            DispatchQueue.main.async {
                guard let self else { return }
                do {
                    let model = try LocalModelOption.inspect(url)
                    if self.localModels.contains(where:{$0.path == model.path}) { self.notice = "这个模型已经在本地模型库中"; return }
                    self.localModels.append(model); self.persistModels(); self.notice = "模型已添加，点击“切换使用”即可加载"
                } catch { self.errorMessage = error.localizedDescription }
            }
        }
    }
    func switchModel(_ id: String) {
        guard !isBusy, !isInspecting, !isApplying, id != selectedModelID, localModels.contains(where:{$0.id == id}) else { return }
        if let model=localModels.first(where:{$0.id==id}),!DevicePolicy.allows(model) {
            errorMessage="这个进阶模型需要至少 32 GB 内存。请切换日常模型。";return
        }
        if let plan = agentPlan, plan.state != "completed" { let request = plan.prompt; newTask(); prompt = request }
        shutdown(); ready = false; networkVerified = false; selectedModelID = id; loadedModelName = ""; persistModels(); errorMessage = nil
        bootMessage = "正在切换到\(selectedModel?.name ?? "本地模型")"
        DispatchQueue.main.asyncAfter(deadline:.now()+0.5) { self.startWorker() }
    }

    func applyTransaction() {
        guard let tx = current?.transaction, ready, !isBusy, !isApplying else { return }
        isApplying = true
        send(["command":"apply","transaction_id":tx.id,"paths":selectedPaths])
    }
    func undoTransaction() {
        guard let tx = current?.transaction, ready, !isBusy, !isApplying else { return }
        isApplying = true
        send(["command":"undo","transaction_id":tx.id])
    }

    func persistHistory() {
        if let data = try? JSONEncoder().encode(history) {
            let path = dataDir.appendingPathComponent("history.json")
            try? data.write(to: path, options: .atomic)
            try? FileManager.default.setAttributes([.posixPermissions:0o600], ofItemAtPath:path.path)
        }
    }

    func exportHistory() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "归屿工作记录.json"
        panel.begin { [weak self] response in
            guard response == .OK, let url = panel.url else { return }
            DispatchQueue.main.async {
                guard let self, let data = try? JSONEncoder().encode(self.history) else { return }
                do { try data.write(to:url,options:.atomic); self.notice = "工作记录已导出到你选择的位置" }
                catch { self.errorMessage = "未能保存，请选择其他位置。" }
            }
        }
    }

    func clearHistory() {
        guard !isBusy, !isApplying else { return }
        // Keep transaction journals and source files so previous file moves remain recoverable.
        history = []; current = nil; activeThreadID = nil; agentPlan = nil; persistPendingPlan(); activePrompt = ""; streamed = ""
        let outputs = dataDir.appendingPathComponent("Outputs")
        try? FileManager.default.removeItem(at: outputs)
        try? FileManager.default.removeItem(at:dataDir.appendingPathComponent("Plans"))
        persistHistory()
        notice = "已清空对话和生成结果，原始资料与文件整理恢复记录已保留"
    }

    func dismissWelcome() {
        showWelcome = false
        try? Data().write(to: baseDataDir.appendingPathComponent("welcomed"))
    }

    func revealStorage() { NSWorkspace.shared.open(dataDir) }
    func openArtifact(_ artifact: Artifact) {
        guard let url = ProductFiles.validatedURL(artifact,dataDir:dataDir) else { errorMessage = "结果文件已移动或删除，可以重新运行这项任务。"; return }
        NSWorkspace.shared.open(url)
    }
    func revealArtifact(_ artifact: Artifact) {
        guard let url = ProductFiles.validatedURL(artifact,dataDir:dataDir) else { errorMessage = "结果文件已移动或不在当前空间。";return }
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }
    func copy(_ text: String) { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(text,forType:.string); notice = "已复制" }
}
