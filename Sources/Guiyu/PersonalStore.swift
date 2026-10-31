import AppKit
import Foundation
import UniformTypeIdentifiers

extension Store {
    func useAdaptiveDemo() {
        guard !contextLocked else { return }
        usePersonalDemo();intelligentExecution = true;kind = .auto
        prompt = "先对比两份场地方案的费用和设备，再核对取消规则。写一份不超过300字的选择说明，分别给出预算优先、需要投影仪时的建议。缺少的信息标为待补充，最后先给我文件整理预览。"
    }
    var workProducts: [WorkProduct] {
        history.sorted { $0.created > $1.created }.flatMap { record in record.artifacts.map {
            var artifact = $0
            if artifact.preview == nil { artifact.preview = record.text }
            if artifact.columns == nil { artifact.columns = record.columns }
            if artifact.rows == nil { artifact.rows = record.rows }
            return WorkProduct(record:record,artifact:artifact)
        } }
    }
    func usePersonalDemo() {
        guard !contextLocked else { return }
        if activeWorkspace != nil { switchWorkspace(nil) }
        let source = Bundle.main.resourceURL!.appendingPathComponent("personal")
        let destination = dataDir.appendingPathComponent("Examples/\(UUID().uuidString)")
        do {
            try FileManager.default.createDirectory(at:destination.deletingLastPathComponent(),withIntermediateDirectories:true)
            try FileManager.default.copyItem(at:source,to:destination)
            newTask();selectedPaths = [destination.path];kind = .auto
            prompt = "对比这两份场地方案的费用、可用时间和设备，按维度保留原文出处，再写一份简短的选择说明。"
            persistScope();if ready { inspect() }
            notice = "已加入两份虚构方案，可以体验对比与写作"
        } catch { errorMessage = "对比示例暂时无法打开，请重新准备应用。" }
    }
    func savePreferences(_ value: PersonalPreferences) -> Bool {
        guard !contextLocked else { return false }
        var saved = value
        saved.notes = String(saved.notes.trimmingCharacters(in:.whitespacesAndNewlines).prefix(600))
        if !PersonalPreferences.tones.contains(saved.tone) { saved.tone = PersonalPreferences.tones[0] }
        if !PersonalPreferences.lengths.contains(saved.length) { saved.length = PersonalPreferences.lengths[0] }
        do {
            try ModelStorage.write(saved,to:baseDataDir.appendingPathComponent("preferences.json"))
            preferences = saved; notice = saved.enabled ? "使用习惯已保存在本机，下次拟定任务时生效" : "已关闭使用习惯，后续只按当前要求表达"
            return true
        } catch { errorMessage = "使用习惯暂时无法保存，请检查本机存储。"; return false }
    }
    func continueProduct(_ product: WorkProduct) {
        guard !contextLocked,product.isComplete else { return }
        openRecord(product.record)
        kind = .write
        if product.record.plan?.steps.contains(where:{$0.tool == "compare"}) == true {
            prompt = "根据上一轮资料对比，写一份简短的选择说明，区分原文事实与建议，保留出处。"
        } else if product.artifact.type == "xlsx" {
            prompt = "把上一轮表格与统计结果写成一份简短说明，保留条件和出处。"
        } else { prompt = "请修改上一轮文稿：表达更简洁，保留原有事实、数字和出处。" }
        notice = "已回到原任务，补充修改要求后即可继续"
    }
    func saveArtifactCopy(_ artifact: Artifact) {
        guard let source = ProductFiles.validatedURL(artifact,dataDir:dataDir) else { errorMessage = "结果文件已移动或不在当前空间，可以查看生成时预览或重新运行。"; return }
        let scopeID = activeWorkspaceID
        let panel = NSSavePanel(); panel.title = "保存一份成果副本"; panel.prompt = "保存副本"
        panel.nameFieldStringValue = source.lastPathComponent
        panel.allowedContentTypes = [UTType(filenameExtension:source.pathExtension)].compactMap { $0 }
        panel.canCreateDirectories = true
        panel.begin { [weak self] response in
            guard response == .OK,let destination = panel.url else { return }
            DispatchQueue.main.async {
                guard let self,self.activeWorkspaceID == scopeID,let current = ProductFiles.validatedURL(artifact,dataDir:self.dataDir) else { return }
                do {
                    // copyItem fails on existing destinations; generated files are never overwritten.
                    try FileManager.default.copyItem(at:current,to:destination)
                    self.notice = "副本已保存，归屿中的原成果仍然保留"
                } catch { self.errorMessage = "副本未保存。如果目标已有同名文件，请换一个名称。" }
            }
        }
    }
}
