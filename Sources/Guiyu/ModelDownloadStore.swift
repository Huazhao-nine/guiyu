import AppKit
import Foundation

extension Store {
    func refreshModelDownloads() {
        let wasUnavailable = selectedModel == nil || selectedModel?.bytes == 0
        var changed=false
        var statuses:[String:ModelDownloadStatus] = [:]
        for item in modelCatalog {
            if let data = try? Data(contentsOf:ModelStorage.status(item.id)),var status = try? JSONDecoder().decode(ModelDownloadStatus.self,from:data) {
                if status.active && Date().timeIntervalSince1970-status.updated>25 { status.phase = "paused"; status.detail = "下载已暂停，点击继续即可恢复" }
                statuses[item.id] = status
            }
            if item.isEmbedding || item.isPrivacy { continue }
            guard let option=PrimaryModel.prepared(item),
                  !localModels.contains(where:{$0.id==option.id && $0.path==option.path && $0.bytes==option.bytes}) else { continue }
            localModels=PrimaryModel.merging(option,into:localModels);changed=true
            notice = "\(item.name) 已准备好，可以切换使用"
        }
        if changed { persistModels() }
        downloadStatuses = statuses
        if wasUnavailable,selectedModel?.bytes ?? 0 > 0,hostSandboxed,!contextLocked { startWorker() }
        if activeWorkspace != nil,embeddingReady,!indexState.semantic,indexState.phase == "ready",!isBusy {
            stopWorkspaceIndex();startWorkspaceIndex()
        }
    }
    func privacyComponentReady(_ item:CatalogModel)->Bool {
        guard item.isPrivacy else { return false }
        let directory=ModelStorage.installed(item.id)
        guard let data=try? Data(contentsOf:directory.appendingPathComponent("guiyu-install.json")),let marker=try? JSONDecoder().decode([String:String].self,from:data),marker["revision"]==item.revision else { return false }
        return item.files.allSatisfy { file in
            let url=directory.appendingPathComponent(file.name)
            guard let values=try? url.resourceValues(forKeys:[.fileSizeKey,.isSymbolicLinkKey]) else { return false }
            return values.isSymbolicLink != true && Int64(values.fileSize ?? -1)==file.bytes
        }
    }
    var embeddingReady:Bool {
        let directory = ModelStorage.installed("bge-small-zh-v1.5")
        guard let model = modelCatalog.first(where:{$0.isEmbedding}),
              let data = try? Data(contentsOf:directory.appendingPathComponent("guiyu-install.json")),
              let marker = try? JSONDecoder().decode([String:String].self,from:data) else { return false }
        return marker["revision"] == model.revision && FileManager.default.fileExists(atPath:directory.appendingPathComponent("model.safetensors").path)
    }
    func installedOption(_ item:CatalogModel)->LocalModelOption? {
        return localModels.first { $0.id == item.id && $0.bytes>0 && FileManager.default.fileExists(atPath:URL(fileURLWithPath:$0.path).appendingPathComponent("config.json").path) }
    }
    var anyDownloadActive: Bool { downloadStatuses.values.contains(where: \.active) }
    func requestModelDownload(_ item:CatalogModel,pause:Bool = false) {
        guard pause || !anyDownloadActive else { return }
        do {
            try FileManager.default.createDirectory(at:ModelStorage.root,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
            let prior = downloadStatuses[item.id]
            let status = ModelDownloadStatus(modelID:item.id,phase:pause ? "pausing" : "starting",completed:prior?.completed ?? 0,total:item.bytes,detail:pause ? "正在暂停并保存进度…" : "正在启动独立下载组件…")
            downloadStatuses[item.id] = status
            try ModelStorage.write(status,to:ModelStorage.status(item.id))
            try ModelStorage.write(["id":UUID().uuidString,"action":pause ? "pause" : "download","modelID":item.id],to:ModelStorage.root.appendingPathComponent("command.json"))
            let helper = Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers/GuiyuModelDownloader.app")
            let config = NSWorkspace.OpenConfiguration(); config.activates = false; config.arguments = ["--serve"]
            NSWorkspace.shared.openApplication(at:helper,configuration:config) { _,error in
                if error != nil { DispatchQueue.main.async {
                    self.errorMessage = "下载组件暂时无法启动，请重新打开归屿后重试。"
                    self.downloadStatuses[item.id]?.phase = "failed"
                } }
            }
        } catch { errorMessage = "无法保存下载请求，请检查磁盘权限。" }
    }
    func removeModel(_ model:LocalModelOption) {
        guard !isBusy,model.id != selectedModelID else { return }
        let url = URL(fileURLWithPath:model.path).standardizedFileURL
        do {
            let managed = ["Installed","Research"].contains { url.path.hasPrefix(ModelStorage.root.appendingPathComponent($0).path+"/") }
            if managed {
                try FileManager.default.trashItem(at:url,resultingItemURL:nil)
                try? FileManager.default.removeItem(at:ModelStorage.status(model.id))
            }
            localModels.removeAll { $0.id == model.id }; persistModels(); refreshModelDownloads()
            notice = managed ? "模型已移到废纸篓" : "模型已从列表移除；原位置的模型文件保留"
        } catch { errorMessage = "暂时无法移除这个模型，请稍后重试。" }
    }
}
