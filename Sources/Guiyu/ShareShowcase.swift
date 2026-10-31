import Foundation
extension Store {
    func useShareDemo() {
        guard !contextLocked,let resources=Bundle.main.resourceURL else { return }
        let id=UUID().uuidString
        let parent=baseDataDir.deletingLastPathComponent().appendingPathComponent("GuiyuExamples/"+id,isDirectory:true)
        let folder=parent.appendingPathComponent("分享副本示例",isDirectory:true)
        do {
            try FileManager.default.createDirectory(at:parent,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
            try FileManager.default.copyItem(at:resources.appendingPathComponent("share-showcase"),to:folder)
            workspaces.append(LocalWorkspace(id:id,name:"分享副本示例",path:folder.path));switchWorkspace(id)
            intelligentExecution=true;kind = .auto
            prompt="把客户跟进纪要.md整理成可分享版本，保留全部正文、预算、办公日期和付款条件。"
            page = .workspace;notice="已加入虚构联系人和密钥，索引就绪后直接发送即可体验。"
        } catch { errorMessage="分享示例暂时无法建立，请检查本机存储后重试。" }
    }
}
