import SwiftUI

struct WorkspaceSwitcher: View {
    @EnvironmentObject var store: Store
    var body:some View {
        Button { store.showWorkspacePicker = true } label: {
            HStack(spacing:10) {
                Image(systemName:store.activeWorkspace == nil ? "house" : "folder.fill").font(.system(size:14)).foregroundStyle(Palette.accent)
                VStack(alignment:.leading,spacing:4) {
                    Text(store.workspaceTitle).font(.system(size:12,weight:.medium)).lineLimit(1)
                    Text(store.activeWorkspace == nil ? "临时资料与日常灵感" : "文件夹工作区").font(.system(size:9)).foregroundStyle(Palette.muted)
                }
                Spacer(minLength:0); Image(systemName:"chevron.up.chevron.down").font(.system(size:9)).foregroundStyle(Palette.muted)
            }.padding(12).background(.white.opacity(0.65),in:RoundedRectangle(cornerRadius:11)).overlay(RoundedRectangle(cornerRadius:11).stroke(Palette.line))
        }.buttonStyle(.plain).disabled(store.contextLocked).accessibilityLabel("切换工作区："+store.workspaceTitle)
    }
}
struct WorkspacePickerView:View {
    @EnvironmentObject var store:Store
    @ViewState private var newName = ""
    var body:some View {
        VStack(alignment:.leading,spacing:22) {
            HStack {
                VStack(alignment:.leading,spacing:9) { Text("让工作，有自己的位置。").font(.custom("Songti SC",size:27)); Text("一个文件夹，一处会自动找资料的空间。").font(.system(size:12)).foregroundStyle(Palette.muted) }
                Spacer(); Button { store.showWorkspacePicker = false } label: { Image(systemName:"xmark.circle.fill").foregroundStyle(Palette.muted) }.buttonStyle(.plain).accessibilityLabel("关闭工作区选择")
            }
            ScrollView {
                VStack(spacing:10) {
                    workspaceRow(nil)
                    ForEach(store.workspaces) { workspace in workspaceRow(workspace) }
                }
            }.frame(minHeight:90,maxHeight:270)
            if store.activeWorkspace != nil {
                HStack { TextField("工作区名称",text:$newName).textFieldStyle(.roundedBorder); Button("保存名称") { if let id = store.activeWorkspaceID { store.renameWorkspace(id,newName) } }.buttonStyle(.bordered).tint(Palette.accent) }.font(.system(size:11))
            }
            Button { store.chooseWorkspace() } label: { Label("选择文件夹，建立工作区",systemImage:"folder.badge.plus").font(.system(size:12,weight:.medium)).padding(.vertical,12).frame(maxWidth:.infinity).foregroundStyle(.white).background(Palette.accent,in:RoundedRectangle(cornerRadius:10)) }.buttonStyle(.plain)
            Button { store.openOfficeShowcase() } label: { Label("体验办公样例工作区",systemImage:"sparkles").font(.system(size:12)).frame(maxWidth:.infinity).padding(12).background(Palette.pale,in:RoundedRectangle(cornerRadius:10)) }.buttonStyle(.plain).foregroundStyle(Palette.accent).disabled(store.contextLocked)
            Text("归屿会在本机读取这个文件夹，建立本地索引并自动跟随文档变化。每个工作区独立保存索引、任务和结果。原文件整理与改名仍需确认。").font(.system(size:10)).foregroundStyle(Palette.muted).lineSpacing(5)
        }.padding(28).frame(width:630).background(Palette.background).onAppear { newName = store.workspaceTitle }
    }
    private func workspaceRow(_ workspace:LocalWorkspace?)->some View {
        let chosen = workspace?.id == store.activeWorkspaceID
        return Button { store.switchWorkspace(workspace?.id); store.showWorkspacePicker = false } label: {
            HStack(spacing:12) {
                Image(systemName:workspace == nil ? "house" : "folder").font(.system(size:20,weight:.light)).foregroundStyle(Palette.accent).frame(width:32)
                VStack(alignment:.leading,spacing:6) {
                    Text(workspace?.name ?? "个人空间").font(.system(size:13,weight:.medium))
                    Text(workspace.map { ($0.path as NSString).abbreviatingWithTildeInPath } ?? "自由添加临时资料，不绑定文件夹").font(.system(size:10)).foregroundStyle(Palette.muted).lineLimit(1).truncationMode(.middle)
                }
                Spacer(); Image(systemName:chosen ? "checkmark.circle.fill" : "chevron.right").font(.system(size:12)).foregroundStyle(chosen ? Palette.accent : Palette.muted)
            }.padding(15).background(.white,in:RoundedRectangle(cornerRadius:12)).overlay(RoundedRectangle(cornerRadius:12).stroke(chosen ? Palette.accent.opacity(0.4) : Palette.line))
        }.buttonStyle(.plain).disabled(store.contextLocked)
    }
}
struct WorkspaceLibraryView:View {
    @EnvironmentObject var store:Store
    @ViewState private var search = ""
    var filtered:[WorkspaceFile] { store.workspaceFiles.filter { search.isEmpty || $0.relativePath.localizedCaseInsensitiveContains(search) } }
    var body:some View {
        VStack(alignment:.leading,spacing:0) {
            header
            Divider().overlay(Palette.line)
            fileList
            footer
        }
    }
    private var header:some View {
            VStack(alignment:.leading,spacing:17) {
                HStack(alignment:.top) {
                    VStack(alignment:.leading,spacing:10) {
                        Text(store.workspaceTitle).font(.custom("Songti SC",size:31))
                        Text(store.workspaceAutomatic ? "直接提出问题，归屿会从整个工作区找到相关资料。" : "勾选本次要用的资料，回到工作台说出你的需求。").font(.system(size:12)).foregroundStyle(Palette.muted)
                    }
                    Spacer(); Button("切换工作区") { store.showWorkspacePicker = true }.buttonStyle(.bordered).tint(Palette.accent).disabled(store.contextLocked)
                }
                HStack { Image(systemName:"folder").foregroundStyle(Palette.accent); Text(((store.activeWorkspace?.path ?? "") as NSString).abbreviatingWithTildeInPath).lineLimit(1).truncationMode(.middle); Spacer(); Button("在访达中打开") { store.revealWorkspace() }.buttonStyle(.plain).foregroundStyle(Palette.accent) }.font(.system(size:10)).foregroundStyle(Palette.muted)
                WorkspaceIndexCard()
                HStack(spacing:12) {
                    HStack(spacing:8) { Image(systemName:"magnifyingglass"); TextField("按文件名或所在文件夹查找",text:$search).textFieldStyle(.plain) }.font(.system(size:12)).padding(11).background(.white,in:RoundedRectangle(cornerRadius:10)).overlay(RoundedRectangle(cornerRadius:10).stroke(Palette.line))
                    Button { store.refreshWorkspace() } label: { Label("刷新",systemImage:"arrow.clockwise") }.buttonStyle(.bordered).disabled(store.contextLocked)
                }
                HStack {
                    Text(store.workspaceScanning ? "正在浏览工作区…" : "\(store.workspaceFiles.count) 份文档 · "+(store.workspaceAutomatic ? "自动按问题选取" : "已选 \(store.selectedPaths.count) / 40 份")).foregroundStyle(Palette.muted)
                    Spacer()
                    if store.workspaceAutomatic { Text("无需逐份勾选").foregroundStyle(Palette.muted) }
                    else {
                        Button("选中当前结果") { store.setWorkspaceSelection(filtered.filter(\.available).map(\.path)) }.disabled(store.contextLocked || filtered.filter(\.available).count>40)
                        Button("取消选择") { store.setWorkspaceSelection([]) }.disabled(store.contextLocked || store.selectedPaths.isEmpty)
                    }
                }.font(.system(size:10)).buttonStyle(.plain).foregroundStyle(Palette.accent)
                if let message = store.workspaceScanMessage { Text(message).font(.system(size:11)).foregroundStyle(Palette.warm) }
            }.padding(30)
    }
    private var fileList:some View {
            ScrollView {
                LazyVStack(spacing:0) {
                    if filtered.isEmpty { VStack(spacing:14) { Image(systemName:"folder.badge.questionmark").font(.system(size:35,weight:.ultraLight)); Text(store.workspaceScanning ? "正在寻找文档" : "这里还没有匹配的文档"); Text("支持文本、PDF、Word、Excel 与 CSV。扫描件暂不支持识别。").font(.system(size:10)) }.foregroundStyle(Palette.muted).frame(maxWidth:.infinity).padding(.vertical,75) }
                    ForEach(filtered) { file in
                        WorkspaceFileRow(file:file)
                        Divider().overlay(Palette.line.opacity(0.5))
                    }
                }.padding(.horizontal,30).padding(.vertical,15)
            }
    }
    private var footer:some View {
            HStack { Label("只在此设备读取 · 原文件保留原处",systemImage:"lock").font(.system(size:10)).foregroundStyle(Palette.muted); Spacer(); Button(store.workspaceAutomatic ? "开始提问 →" : "使用所选资料 →") { store.page = .workspace }.buttonStyle(.borderedProminent).tint(Palette.accent).disabled((!store.workspaceAutomatic && store.selectedPaths.isEmpty) || store.contextLocked) }.padding(25)
        }
}

struct WorkspaceFileRow:View {
    @EnvironmentObject var store:Store
    let file:WorkspaceFile
    private var selected:Bool { store.selectedPaths.contains(file.path) }
    var body:some View {
        Button { store.toggleWorkspaceFile(file) } label: {
            HStack(spacing:13) {
                Image(systemName:selected ? "checkmark.square.fill" : "square").font(.system(size:17)).foregroundStyle(selected ? Palette.accent : Palette.muted.opacity(0.5))
                Image(systemName:["csv","xlsx"].contains(URL(fileURLWithPath:file.path).pathExtension) ? "tablecells" : "doc.text").font(.system(size:19,weight:.light)).foregroundStyle(Palette.accent)
                VStack(alignment:.leading,spacing:6) {
                    Text(file.name).font(.system(size:12,weight:.medium))
                    Text(file.relativePath).font(.system(size:10)).foregroundStyle(Palette.muted).lineLimit(1).truncationMode(.middle)
                }
                Spacer()
                Text(file.available ? ByteCountFormatter.string(fromByteCount:file.bytes,countStyle:.file) : "超过 8 MB").font(.system(size:10)).foregroundStyle(file.available ? Palette.muted : Palette.warm)
            }.padding(.horizontal,16).padding(.vertical,15).background(selected ? Palette.pale.opacity(0.3) : Color.white.opacity(0.5))
        }.buttonStyle(.plain).disabled(store.contextLocked || !file.available).accessibilityLabel((selected ? "取消选择 " : "选择 ")+file.relativePath)
    }
}
