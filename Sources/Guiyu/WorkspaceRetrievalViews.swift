import SwiftUI

struct WorkspaceIndexCard:View {
    @EnvironmentObject var store:Store
    var compact = false
    var body:some View {
        VStack(alignment:.leading,spacing:11) {
            HStack(spacing:8) {
                if store.indexState.active { ProgressView().controlSize(.small) }
                else { Image(systemName:store.indexState.phase == "ready" ? "checkmark.circle.fill" : "exclamationmark.circle").foregroundStyle(store.indexState.phase == "ready" ? Palette.accent : Palette.warm) }
                Text(store.indexState.phase == "ready" ? "工作区已可检索" : store.indexState.message).font(.system(size:compact ? 11 : 12,weight:.medium)).lineLimit(2)
                Spacer(minLength:0)
                if !compact { Label(store.indexUserPaused ? "已暂停" : "自动更新",systemImage:"arrow.triangle.2.circlepath").font(.system(size:10)).foregroundStyle(Palette.accent) }
            }
            HStack(spacing:8) {
                Text("\(store.indexState.indexed) 份资料 · \(store.indexState.chunks) 个片段")
                if !compact { Text("·");Text(store.indexState.semantic ? "本地语义 + 关键词" : "关键词检索") }
            }.font(.system(size:10)).foregroundStyle(Palette.muted)
            if !store.indexState.semantic && !store.indexState.active {
                Button("准备中文语义模型（96 MB）") { store.showModelLibrary = true }.font(.system(size:10)).buttonStyle(.plain).foregroundStyle(Palette.accent)
            }
            if !compact {
                HStack(spacing:8) {
                    modeButton("自动找资料",true)
                    modeButton("手动选择",false)
                    Spacer()
                    Button(store.indexUserPaused ? "建立索引" : "重新建立索引") { store.requestIndexSync(rebuild:true) }.font(.system(size:10)).buttonStyle(.plain).foregroundStyle(Palette.muted).disabled(store.indexState.active || store.isBusy)
                }
                HStack {
                    Text("索引只保存在本机，可随时清空。").font(.system(size:9)).foregroundStyle(Palette.muted)
                    Spacer()
                    Button("清空索引并暂停") { store.clearWorkspaceIndex() }.font(.system(size:9)).buttonStyle(.plain).foregroundStyle(Palette.muted).disabled(store.contextLocked || store.indexState.active || store.indexUserPaused)
                }
                if !store.indexState.notes.isEmpty {
                    ForEach(store.indexState.notes,id:\.self) { Text($0).font(.system(size:10)).foregroundStyle(Palette.warm).lineSpacing(3) }
                }
                if store.indexState.updated>0 {
                    Text("最近检查 "+Date(timeIntervalSince1970:store.indexState.updated).formatted(date:.omitted,time:.standard)+" · 每份最多读取 60,000 字符").font(.system(size:9)).foregroundStyle(Palette.muted)
                }
            } else {
                Button(store.workspaceAutomatic ? "自动从工作区找资料 →" : "当前手动选择资料 →") { store.page = .library }.font(.system(size:10)).buttonStyle(.plain).foregroundStyle(Palette.accent)
            }
        }.padding(compact ? 13 : 16).background(Palette.pale.opacity(0.5),in:RoundedRectangle(cornerRadius:12)).overlay(RoundedRectangle(cornerRadius:12).stroke(Palette.line))
    }
    private func modeButton(_ title:String,_ enabled:Bool)->some View {
        Button { store.setWorkspaceAutomatic(enabled) } label: {
            HStack(spacing:5) { Image(systemName:enabled ? "sparkle.magnifyingglass" : "checklist");Text(title) }.font(.system(size:10,weight:.medium)).foregroundStyle(store.workspaceAutomatic == enabled ? .white : Palette.accent).padding(.horizontal,11).padding(.vertical,8).background(store.workspaceAutomatic == enabled ? Palette.accent : .white.opacity(0.8),in:RoundedRectangle(cornerRadius:8))
        }.buttonStyle(.plain).disabled(store.contextLocked)
    }
}
struct RetrievalEvidenceView:View {
    @EnvironmentObject var store:Store
    let evidence:RetrievalEvidence
    @ViewState private var expanded = false
    var files:[RetrievalHit] { var seen = Set<String>();return evidence.hits.filter { seen.insert($0.path).inserted } }
    var body:some View {
        VStack(alignment:.leading,spacing:11) {
            Button { withAnimation { expanded.toggle() } } label: {
                HStack(spacing:8) { Image(systemName:"sparkle.magnifyingglass").foregroundStyle(Palette.accent);Text(evidence.refreshed ? "资料已更新，本轮使用最新版本" : "已从工作区找到相关资料").font(.system(size:11,weight:.medium));Spacer();Text("\(files.count) / \(evidence.indexed) 份").font(.system(size:10)).foregroundStyle(Palette.muted);Image(systemName:expanded ? "chevron.up" : "chevron.down").font(.system(size:9)).foregroundStyle(Palette.muted) }
            }.buttonStyle(.plain)
            Text(evidence.scopeNote).font(.system(size:10)).foregroundStyle(Palette.muted).lineSpacing(4)
            if expanded {
                ForEach(files) { hit in
                    VStack(alignment:.leading,spacing:6) {
                        HStack { Button(hit.name) { store.previewSource = SourceDoc(["id":"检索","name":hit.name,"path":hit.path,"preview":hit.snippet]) }.buttonStyle(.plain).foregroundStyle(Palette.accent);Spacer();Text(hit.reason).foregroundStyle(Palette.muted) }.font(.system(size:10))
                        Text("第\(hit.line)行 · "+hit.snippet).font(.system(size:10)).foregroundStyle(Palette.ink.opacity(0.85)).lineSpacing(4).lineLimit(5).textSelection(.enabled)
                    }.padding(.top,6)
                }
            }
        }.padding(14).background(Palette.sidebar.opacity(0.6),in:RoundedRectangle(cornerRadius:12)).overlay(RoundedRectangle(cornerRadius:12).stroke(Palette.line.opacity(0.8)))
    }
}
