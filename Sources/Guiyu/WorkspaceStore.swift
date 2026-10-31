import AppKit
import Foundation

extension Store {
    var activeWorkspace: LocalWorkspace? { workspaces.first { $0.id == activeWorkspaceID } }
    var workspaceTitle: String { activeWorkspace?.name ?? "个人空间" }
    var contextLocked: Bool { isBusy || isInspecting || isApplying || workspaceScanning }

    func loadWorkspaceState() {
        try? FileManager.default.createDirectory(at:dataDir,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        history = []
        if let data = try? Data(contentsOf:dataDir.appendingPathComponent("history.json")),let saved = try? JSONDecoder().decode([TaskRecord].self,from:data) { history = saved }
        selectedPaths = [];workspaceAutomatic = true;indexUserPaused = false
        if let data = try? Data(contentsOf:dataDir.appendingPathComponent("scope.json")),let saved = try? JSONDecoder().decode(WorkspaceScope.self,from:data) {
            workspaceAutomatic = saved.automatic ?? true;indexUserPaused = saved.indexPaused ?? false
            selectedPaths = saved.paths.filter { path in activeWorkspace.map { WorkspaceScanner.contains(path,in:$0.path) } ?? true }
        }
        let pending = dataDir.appendingPathComponent("pending-plan.json")
        if let data = try? Data(contentsOf:pending),var saved = try? JSONDecoder().decode(AgentPlan.self,from:data),saved.paths.allSatisfy({ path in activeWorkspace.map { WorkspaceScanner.contains(path,in:$0.path) } ?? true }) {
            if saved.state == "running" { saved.state = "paused" }
            agentPlan = saved; activePrompt = saved.prompt; activeThreadID = saved.threadID; selectedPaths = saved.paths
        }
    }
    func persistWorkspaceRegistry() {
        try? ModelStorage.write(WorkspaceRegistry(selectedID:activeWorkspaceID,workspaces:workspaces),to:baseDataDir.appendingPathComponent("workspaces.json"))
    }
    func persistScope() {
        try? ModelStorage.write(WorkspaceScope(paths:selectedPaths,automatic:workspaceAutomatic,indexPaused:indexUserPaused),to:dataDir.appendingPathComponent("scope.json"))
    }
    func chooseWorkspace() {
        guard !contextLocked else { return }
        let panel = NSOpenPanel(); panel.title = "给工作区选一个文件夹"; panel.prompt = "设为工作区"
        panel.message = "在本机为这个文件夹建立检索索引，归屿可按问题自动找资料。原文件保留在原位置。"
        panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = false
        panel.begin { [weak self] response in
            guard response == .OK,let url = panel.url else { return }
            DispatchQueue.main.async {
                guard let self else { return }
                let resolved = url.resolvingSymlinksInPath().standardizedFileURL
                if let existing = self.workspaces.first(where:{$0.path == resolved.path}) { self.switchWorkspace(existing.id); return }
                let item = LocalWorkspace(id:UUID().uuidString,name:resolved.lastPathComponent,path:resolved.path)
                self.workspaces.append(item); self.switchWorkspace(item.id); self.notice = "工作区已建立，资料仅在本机使用"
            }
        }
    }
    func switchWorkspace(_ id:String?) {
        guard !contextLocked, id != activeWorkspaceID, id == nil || workspaces.contains(where:{$0.id == id}) else { return }
        persistPendingPlan(); persistScope(); shutdown()
        ready = false; networkVerified = false
        resetContext(); documents = []; selectedPaths = []; workspaceFiles = []; workspaceScanMessage = nil
        activeWorkspaceID = id; persistWorkspaceRegistry(); loadWorkspaceState()
        page = .workspace; showWorkspacePicker = false
        if activeWorkspace != nil { refreshWorkspace() }
        startWorker()
    }
    func renameWorkspace(_ id:String,_ name:String) {
        let value = name.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !value.isEmpty,let i = workspaces.firstIndex(where:{$0.id == id}) else { return }
        workspaces[i].name = String(value.prefix(40)); persistWorkspaceRegistry()
    }
    func refreshWorkspace() {
        guard let workspace = activeWorkspace,!isBusy,!isApplying,!isInspecting,!workspaceScanning else { return }
        workspaceScanning = true; workspaceScanMessage = nil
        DispatchQueue.global(qos:.userInitiated).async {
            let result = Result { try WorkspaceScanner.scan(workspace.path) }
            DispatchQueue.main.async {
                guard self.activeWorkspaceID == workspace.id else { return }
                self.workspaceScanning = false
                switch result {
                case .success(let inventory):
                    self.workspaceFiles = inventory.files
                    let valid = Set(inventory.files.filter(\.available).map(\.path))
                    let old = self.selectedPaths
                    self.selectedPaths = old.filter { valid.contains($0) }
                    // On first visit, a small folder is ready without another selection step.
                    let marker = self.dataDir.appendingPathComponent("workspace-initialized")
                    if !FileManager.default.fileExists(atPath:marker.path) {
                        if !self.workspaceAutomatic && valid.count<=40 { self.selectedPaths = inventory.files.filter(\.available).map(\.path) }
                        try? Data().write(to:marker)
                    }
                    if inventory.limited { self.workspaceScanMessage = "当前展示前 2,000 份文档或 20,000 个目录项。可选择更具体的子文件夹作为工作区。" }
                    if !self.workspaceAutomatic && self.selectedPaths != old { self.resetContext(); self.persistPendingPlan(); self.documents = [] }
                    self.persistScope()
                    if self.ready && !self.workspaceAutomatic { self.inspect() }
                case .failure:
                    self.workspaceFiles = []; self.documents = []; self.selectedPaths = []; self.resetContext(); self.persistScope()
                    self.workspaceScanMessage = "工作区暂时无法读取，请检查文件夹是否已移动、磁盘是否连接，以及访问权限。"
                }
            }
        }
    }
    func setWorkspaceSelection(_ paths:[String]) {
        guard !contextLocked,activeWorkspace != nil else { return }
        let valid = Set(workspaceFiles.filter(\.available).map(\.path))
        let selected = Array(Set(paths)).filter { valid.contains($0) }.sorted()
        guard selected.count<=40 else { errorMessage = "每次任务最多使用 40 份资料。请缩小选择。"; return }
        workspaceAutomatic = false
        resetContext(); persistPendingPlan(); selectedPaths = selected; documents = []; persistScope()
        if ready { inspect() }
    }
    func toggleWorkspaceFile(_ file:WorkspaceFile) {
        var paths = selectedPaths
        if paths.contains(file.path) { paths.removeAll { $0 == file.path } } else { paths.append(file.path) }
        setWorkspaceSelection(paths)
    }
    func revealWorkspace() { if let workspace = activeWorkspace { NSWorkspace.shared.open(URL(fileURLWithPath:workspace.path)) } }
}
