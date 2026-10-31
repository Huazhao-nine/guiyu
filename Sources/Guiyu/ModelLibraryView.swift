import SwiftUI

struct ModelLibraryView: View {
    @EnvironmentObject var store: Store
    @ViewState private var tab = "discover"
    @ViewState private var removal:LocalModelOption?
    @ViewState private var confirmRemoval = false
    var body: some View {
        VStack(alignment:.leading,spacing:19) {
            HStack(alignment:.top) {
                VStack(alignment:.leading,spacing:9) {
                    Text("你的本地搭档").font(.custom("Songti SC",size:30))
                    Text("一个模型，负责理解目标、调用工具和核对交付。无需手动切换。").font(.system(size:12)).foregroundStyle(Palette.muted)
                }
                Spacer()
                Button { store.showModelLibrary = false } label: { Image(systemName:"xmark.circle.fill").font(.system(size:19)).foregroundStyle(Palette.muted) }.buttonStyle(.plain).accessibilityLabel("关闭模型库")
            }
            HStack(spacing:8) {
                Label("以 32 GB 为开发基准",systemImage:"desktopcomputer").font(.system(size:10,weight:.medium))
                Text("·"); Text("当前设备 \(DevicePolicy.deviceMemoryGB) GB · 单模型运行").font(.system(size:10))
                Spacer(); Text("本地运行 · MLX").font(.system(size:9,weight:.medium))
            }.foregroundStyle(Palette.accent).padding(12).background(Palette.pale.opacity(0.7),in:RoundedRectangle(cornerRadius:10))
            HStack {
                HStack(spacing:3) {
                    modelTab("为你推荐","discover")
                    modelTab("已在本机","installed")
                }.padding(3).background(Palette.sidebar,in:RoundedRectangle(cornerRadius:9))
                Spacer()
                Button { store.addLocalModel() } label: { Label("导入已有模型",systemImage:"folder.badge.plus").font(.system(size:10)) }.buttonStyle(.plain).foregroundStyle(Palette.muted).disabled(store.contextLocked)
            }
            ScrollView {
                VStack(spacing:12) {
                    if tab == "discover" {
                        ForEach(store.modelCatalog.filter { !$0.isEmbedding && !$0.isPrivacy && ($0.recommended == true || $0.advanced == true) }) { model in modelCard(model) }
                        ForEach(store.modelCatalog.filter { $0.isEmbedding }) { model in
                            if store.embeddingReady { embeddingCard } else { modelCard(model) }
                        }
                    } else {
                        if store.embeddingReady { embeddingCard }
                        ForEach(store.localModels.filter { $0.bytes>0 }) { model in installedCard(model) }
                        if store.localModels.filter({$0.bytes>0}).isEmpty { Text("还没有模型。前往“为你推荐”，下载你的第一位搭档。").font(.system(size:12)).foregroundStyle(Palette.muted).padding(35) }
                    }
                }.padding(1)
            }.frame(height:390)
            HStack(alignment:.top,spacing:10) {
                Image(systemName:"arrow.down.shield").font(.system(size:17,weight:.light)).foregroundStyle(Palette.accent)
                VStack(alignment:.leading,spacing:6) {
                    Text("仅下载模型，资料处理始终在本机").font(.system(size:11,weight:.medium))
                    Text("下载组件从 Hugging Face 获取模型，并从 PyPI 获取固定的隐私运行组件；不接收文档、对话和工作区路径。下载会向模型源暴露 IP 地址与所选模型。内存为起步估计，实际用量随任务长度变化。").font(.system(size:10)).foregroundStyle(Palette.muted).lineSpacing(4)
                }
            }.padding(14).background(Palette.sidebar.opacity(0.7),in:RoundedRectangle(cornerRadius:11))
            if let error = store.errorMessage { Text(error).font(.system(size:11)).foregroundStyle(Palette.warm).lineLimit(3) }
        }.padding(28).frame(width:760).background(Palette.background)
    }
    private var embeddingCard:some View {
        VStack(alignment:.leading,spacing:9) {
            HStack { Image(systemName:"sparkle.magnifyingglass");Text("BGE 中文语义检索").fontWeight(.medium);Spacer();Text("工作区自动使用") }
            Text("96.4 MB · MIT · 用于理解问题并匹配相关资料，无需切换对话模型。")
        }.font(.system(size:11)).foregroundStyle(Palette.accent).padding(17).background(Palette.pale,in:RoundedRectangle(cornerRadius:12))
    }
    private func modelTab(_ title:String,_ key:String)->some View {
        Button { tab = key } label: {
            Text(title).font(.system(size:11,weight:tab == key ? .medium : .regular)).foregroundStyle(tab == key ? Palette.accent : Palette.muted).padding(.horizontal,16).padding(.vertical,8).background(tab == key ? Color.white : Color.clear,in:RoundedRectangle(cornerRadius:7))
        }.buttonStyle(.plain)
    }
    private func modelCard(_ item:CatalogModel)->some View {
        let installed = store.installedOption(item)
        let status = store.downloadStatuses[item.id]
        return VStack(alignment:.leading,spacing:12) {
            HStack(spacing:13) {
                Image(systemName:item.recommended == true ? "sparkles" : "cpu").font(.system(size:23,weight:.light)).foregroundStyle(Palette.accent).frame(width:48,height:48).background(Palette.pale,in:RoundedRectangle(cornerRadius:12))
                VStack(alignment:.leading,spacing:6) {
                    HStack(spacing:9) { Text(item.name).font(.system(size:15,weight:.semibold)); Text(item.badge).font(.system(size:9,weight:.medium)).foregroundStyle(Palette.accent).padding(.horizontal,7).padding(.vertical,4).background(Palette.pale,in:Capsule()) }
                    Text("下载 \(ByteCountFormatter.string(fromByteCount:item.bytes,countStyle:.file)) · \(item.memory)").font(.system(size:10)).foregroundStyle(Palette.muted)
                }
                Spacer(minLength:5)
                if item.isEmbedding && store.embeddingReady { Label("检索已准备",systemImage:"checkmark.circle.fill").font(.system(size:10)).foregroundStyle(Palette.accent) }
                else if let installed { modelAction(installed) }
                else if status?.active == true {
                    Button(status?.phase == "pausing" ? "正在暂停" : "暂停") { store.requestModelDownload(item,pause:true) }.font(.system(size:11)).buttonStyle(.bordered).tint(Palette.accent).disabled(status?.phase == "pausing")
                } else {
                    Button { store.requestModelDownload(item) } label: { Label(status == nil ? "一键下载" : status?.phase == "paused" ? "继续下载" : "重试下载",systemImage:"arrow.down").font(.system(size:11,weight:.medium)).padding(.horizontal,10).padding(.vertical,8).foregroundStyle(.white).background(Palette.accent,in:RoundedRectangle(cornerRadius:8)) }.buttonStyle(.plain).disabled(store.anyDownloadActive)
                }
            }
            Text(item.summary).font(.system(size:11)).foregroundStyle(Palette.ink.opacity(0.85)).lineSpacing(4)
            if installed == nil && !(item.isEmbedding && store.embeddingReady),let status {
                VStack(alignment:.leading,spacing:7) {
                    ProgressView(value:status.progress).tint(Palette.accent)
                    HStack { Text(status.detail).lineLimit(1); Spacer(); Text("\(ByteCountFormatter.string(fromByteCount:status.completed,countStyle:.file)) / \(ByteCountFormatter.string(fromByteCount:status.total,countStyle:.file))") }.font(.system(size:9)).foregroundStyle(status.phase == "failed" ? Palette.warm : Palette.muted)
                }
            }
            HStack(spacing:8) { Text(item.license); Text("·"); Text("固定版本 \(item.revision.prefix(7))"); Spacer(); Text((installed != nil || (item.isEmbedding && store.embeddingReady)) ? "已在本机" : "校验后才可使用") }.font(.system(size:9)).foregroundStyle(Palette.muted)
        }.padding(17).background(.white,in:RoundedRectangle(cornerRadius:14)).overlay(RoundedRectangle(cornerRadius:14).stroke(item.recommended == true ? Palette.accent.opacity(0.35) : Palette.line))
    }
    @ViewBuilder private func modelAction(_ model:LocalModelOption)->some View {
        if model.id == store.selectedModelID {
            Label(store.ready ? "使用中" : "加载中",systemImage:store.ready ? "checkmark.circle.fill" : "clock").font(.system(size:10,weight:.medium)).foregroundStyle(Palette.accent)
        } else {
            Button("切换使用") { store.switchModel(model.id) }.font(.system(size:11)).buttonStyle(.bordered).tint(Palette.accent).disabled(store.contextLocked || !DevicePolicy.allows(model))
        }
    }
    private func installedCard(_ model:LocalModelOption)->some View {
        VStack(alignment:.leading,spacing:12) {
            HStack { Image(systemName:"cpu").foregroundStyle(Palette.accent); Text(model.name).font(.system(size:14,weight:.medium)); Spacer(); modelAction(model) }
            Text(model.detail).font(.system(size:10)).foregroundStyle(Palette.muted)
            if model.bytes > 7 * 1024 * 1024 * 1024 {
                Text("需要 32 GB 内存 · 单模型运行").font(.system(size:10)).foregroundStyle(Palette.muted)
            }
            Text((model.path as NSString).abbreviatingWithTildeInPath).font(.system(size:9)).foregroundStyle(Palette.muted).lineLimit(1).truncationMode(.middle)
            if model.id != "default-qwen3" && model.id != store.selectedModelID {
                Button("移除模型…") { removal = model; confirmRemoval = true }.font(.system(size:10)).buttonStyle(.plain).foregroundStyle(Palette.warm).disabled(store.contextLocked)
            }
        }.padding(18).background(.white,in:RoundedRectangle(cornerRadius:13)).overlay(RoundedRectangle(cornerRadius:13).stroke(Palette.line))
        .alert("移除这个模型？",isPresented:$confirmRemoval) {
            Button("取消",role:.cancel) { removal = nil }
            Button("移除",role:.destructive) { if let removal { store.removeModel(removal) }; removal = nil }
        } message: { Text("归屿下载的模型会移到废纸篓；自行导入的模型只从列表移除。工作记录会保留。") }
    }
}
