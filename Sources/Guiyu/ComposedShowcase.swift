import Foundation

extension Store {
    func useComposedDemo() {
        guard !contextLocked,let resources=Bundle.main.resourceURL else { return }
        let id=UUID().uuidString
        let parent=baseDataDir.deletingLastPathComponent().appendingPathComponent("GuiyuExamples/"+id,isDirectory:true)
        let folder=parent.appendingPathComponent("筹备任务示例",isDirectory:true)
        do {
            try FileManager.default.createDirectory(at:parent,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
            try FileManager.default.copyItem(at:resources.appendingPathComponent("composed-showcase"),to:folder)
            workspaces.append(LocalWorkspace(id:id,name:"筹备任务示例",path:folder.path))
            switchWorkspace(id)
            intelligentExecution=true;kind = .auto
            prompt="只用活动方案.md，计算全部筹备费用和剩余预算，核对活动日期提前7天是哪一天，再写一份简短筹备说明，导出Word。保留费用尚未付款这一条件。"
            page = .workspace;notice="已加入两份虚构资料，索引就绪后即可体验预算、日期与写作协作"
        } catch { errorMessage="样例暂时无法建立，请检查本机存储后重试。" }
    }
}
