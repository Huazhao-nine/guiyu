import Foundation

extension Store {
    func useRosterDemo() {
        guard !contextLocked,let resources=Bundle.main.resourceURL else { return }
        let id=UUID().uuidString
        let parent=baseDataDir.deletingLastPathComponent().appendingPathComponent("GuiyuExamples/"+id,isDirectory:true)
        let folder=parent.appendingPathComponent("名单筛选示例",isDirectory:true)
        do {
            try FileManager.default.createDirectory(at:parent,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
            try FileManager.default.copyItem(at:resources.appendingPathComponent("roster-showcase"),to:folder)
            workspaces.append(LocalWorkspace(id:id,name:"名单筛选示例",path:folder.path));switchWorkspace(id)
            intelligentExecution=true;kind = .auto
            prompt="在我给你的工作簿 1 文件中，把计算技术研究所的同学的名单分离出来，发给我。"
            page = .workspace;notice="虚构名单分在两个工作表。直接发送即可筛选，完成后可继续说“那软件研究所呢？”"
        } catch { errorMessage="名单示例暂时无法建立，请检查本机存储后重试。" }
    }
}
