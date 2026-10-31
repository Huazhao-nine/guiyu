import SwiftUI

struct WorkProductsView: View {
    @EnvironmentObject var store: Store
    @ViewState private var search = ""
    @ViewState private var format = "全部"
    private var products: [WorkProduct] {
        let query = search.trimmingCharacters(in:.whitespacesAndNewlines)
        return store.workProducts.filter { item in
            (format == "全部" || item.artifact.type == format.lowercased()) &&
            (query.isEmpty || (item.title+" "+item.artifact.name+" "+(item.artifact.preview ?? "")).localizedCaseInsensitiveContains(query))
        }
    }
    var body: some View {
        ScrollView {
            VStack(alignment:.leading,spacing:24) {
                HStack(alignment:.top) {
                    VStack(alignment:.leading,spacing:12) {
                        Text("做过的事，接着做好。").font(.custom("Songti SC",size:34))
                        Text("在\(store.workspaceTitle)找回文稿与表格，带着原来的资料继续。")
                            .font(.system(size:12)).foregroundStyle(Palette.muted)
                    }
                    Spacer()
                    Image(systemName:"tray.full").font(.system(size:37,weight:.ultraLight)).foregroundStyle(Palette.accent.opacity(0.7))
                }
                HStack(spacing:16) {
                    stat("\(store.workProducts.count)","份本机成果","doc.on.doc")
                    stat("\(Set(store.workProducts.map { $0.record.id }).count)","项工作留下结果","checkmark.circle")
                    stat("可接着做","原资料与任务一起保留","arrow.triangle.branch")
                }
                HStack(spacing:12) {
                    HStack(spacing:10) {
                        Image(systemName:"magnifyingglass").foregroundStyle(Palette.muted)
                        TextField("按任务、文件名或生成内容查找",text:$search).textFieldStyle(.plain).font(.system(size:12))
                        if !search.isEmpty { Button { search = "" } label: { Image(systemName:"xmark.circle.fill").foregroundStyle(Palette.muted) }.buttonStyle(.plain).help("清除成果搜索") }
                    }.padding(14).background(.white,in:RoundedRectangle(cornerRadius:11)).overlay(RoundedRectangle(cornerRadius:11).stroke(Palette.line))
                    Picker("文件类型",selection:$format) { ForEach(["全部","DOCX","XLSX","MD"],id:\.self) { Text($0).tag($0) } }.labelsHidden().pickerStyle(.segmented).frame(width:255)
                }
                HStack { Text("\(products.count) 份成果").font(.system(size:10)).foregroundStyle(Palette.muted); Spacer(); Label("只保存在此设备",systemImage:"lock").font(.system(size:10)).foregroundStyle(Palette.accent) }
                if products.isEmpty {
                    VStack(spacing:16) {
                        Image(systemName:search.isEmpty ? "doc.badge.plus" : "doc.text.magnifyingglass").font(.system(size:36,weight:.ultraLight)).foregroundStyle(Palette.accent)
                        Text(search.isEmpty && format == "全部" ? "下一份成果，从一个想法开始。" : "换个关键词，再找找。").font(.custom("Songti SC",size:22))
                        Text("当前空间生成的文稿、表格与对比结果会出现在这里。").font(.system(size:11)).foregroundStyle(Palette.muted)
                        Button("回工作台 →") { store.page = .workspace }.buttonStyle(.plain).foregroundStyle(Palette.accent).font(.system(size:12))
                    }.frame(maxWidth:.infinity).padding(.vertical,70).card()
                } else {
                    LazyVGrid(columns:[GridItem(.adaptive(minimum:330),spacing:16)],spacing:16) {
                        ForEach(products) { product in WorkProductCard(product:product) }
                    }
                }
                if let error = store.errorMessage { ErrorBanner(message:error) }
                Text("预览保留生成时的内容。继续加工会回到原任务；资料变化时会重新读取。当前显示本空间最近保留的工作记录。")
                    .font(.system(size:10)).foregroundStyle(Palette.muted).lineSpacing(5)
            }.padding(36)
        }
    }
    private func stat(_ value:String,_ title:String,_ icon:String)->some View {
        HStack(spacing:13) {
            Image(systemName:icon).font(.system(size:20,weight:.light)).foregroundStyle(Palette.accent)
            VStack(alignment:.leading,spacing:6) { Text(value).font(.system(size:18,weight:.medium)); Text(title).font(.system(size:10)).foregroundStyle(Palette.muted) }
            Spacer(minLength:0)
        }.padding(20).frame(maxWidth:.infinity,alignment:.leading).card()
    }
}

struct WorkProductCard: View {
    @EnvironmentObject var store: Store
    let product: WorkProduct
    private var artifact: Artifact { product.artifact }
    private var previewText: String {
        if artifact.type == "xlsx",let rows = artifact.rows,!rows.isEmpty {
            return "\(rows.count) 行 · \(artifact.columns?.count ?? 0) 列\n"+rows.prefix(2).map { $0.joined(separator:" · ") }.joined(separator:"\n")
        }
        return (artifact.preview ?? product.record.text).components(separatedBy:"\n")
            .filter { !$0.trimmingCharacters(in:.whitespaces).hasPrefix("|") }
            .joined(separator:"\n").replacingOccurrences(of:"#",with:"").replacingOccurrences(of:"**",with:"")
    }
    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            HStack(spacing:12) {
                Image(systemName:["xlsx","csv"].contains(artifact.type) ? "tablecells" : "doc.text").font(.system(size:23,weight:.light)).foregroundStyle(Palette.accent).frame(width:43,height:48).background(Palette.pale,in:RoundedRectangle(cornerRadius:10))
                VStack(alignment:.leading,spacing:6) {
                    Text(artifact.name).font(.system(size:13,weight:.medium)).lineLimit(1)
                    Text(artifact.type.uppercased()+" · "+Date(timeIntervalSince1970:product.record.created).formatted(.dateTime.locale(Locale(identifier:"zh_CN")).month().day().hour().minute()))
                        .font(.system(size:9)).foregroundStyle(Palette.muted)
                }
                Spacer(minLength:0)
                if !product.isComplete { Text("阶段成果").font(.system(size:9)).foregroundStyle(Palette.warm) }
            }
            Text(product.title).font(.system(size:11,weight:.medium)).lineLimit(2).lineSpacing(4).frame(height:36,alignment:.top)
            Text(String(previewText.prefix(180)))
                .font(.system(size:10)).foregroundStyle(Palette.muted).lineLimit(3).lineSpacing(4).frame(height:48,alignment:.top)
            Rectangle().fill(Palette.line).frame(height:1)
            HStack(spacing:18) {
                Button("预览") { store.previewArtifact = artifact }.font(.system(size:11,weight:.medium))
                Button("继续加工") { store.continueProduct(product) }.disabled(store.contextLocked || !product.isComplete).font(.system(size:11))
                Spacer()
                Button { store.saveArtifactCopy(artifact) } label: { Image(systemName:"square.and.arrow.up").font(.system(size:13)) }.help("保存一份副本")
            }.buttonStyle(.plain).foregroundStyle(Palette.accent)
        }.padding(21).frame(maxWidth:.infinity,alignment:.leading).card()
    }
}

struct PersonalPreferencesView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) var dismiss
    @ViewState private var draft = PersonalPreferences()
    var body: some View {
        VStack(alignment:.leading,spacing:22) {
            HStack {
                Label("按你的习惯，慢慢熟悉你。",systemImage:"slider.horizontal.3").font(.custom("Songti SC",size:25))
                Spacer()
                Button { dismiss() } label: { Image(systemName:"xmark.circle.fill").foregroundStyle(Palette.muted) }.buttonStyle(.plain).help("关闭使用习惯")
            }
            Text("只记住你在这里明确保存的表达偏好。可随时修改或关闭，当前任务要求始终优先。")
                .font(.system(size:12)).foregroundStyle(Palette.muted).lineSpacing(5)
            Toggle("在新的写作与问答中使用这些习惯",isOn:$draft.enabled).toggleStyle(.switch).font(.system(size:12)).tint(Palette.accent)
            VStack(alignment:.leading,spacing:20) {
                HStack { Text("喜欢的语气").font(.system(size:12)); Spacer(); Picker("语气",selection:$draft.tone) { ForEach(PersonalPreferences.tones,id:\.self) { Text($0).tag($0) } }.labelsHidden().frame(width:240) }
                HStack { Text("默认篇幅").font(.system(size:12)); Spacer(); Picker("篇幅",selection:$draft.length) { ForEach(PersonalPreferences.lengths,id:\.self) { Text($0).tag($0) } }.labelsHidden().pickerStyle(.segmented).frame(width:240) }
                VStack(alignment:.leading,spacing:9) {
                    HStack { Text("还有哪些表达习惯？").font(.system(size:12)); Spacer(); Text("\(draft.notes.count) / 600").font(.system(size:9)).foregroundStyle(Palette.muted) }
                    TextEditor(text:$draft.notes).font(.system(size:12)).scrollContentBackground(.hidden).frame(height:100).padding(10).background(Palette.background,in:RoundedRectangle(cornerRadius:9)).overlay(RoundedRectangle(cornerRadius:9).stroke(Palette.line))
                    Text("例如：先说结论；少用客套话；专业名词附上通俗解释。无需填写私密身份资料。")
                        .font(.system(size:10)).foregroundStyle(Palette.muted).lineSpacing(4)
                }
            }.padding(20).background(.white,in:RoundedRectangle(cornerRadius:13)).opacity(draft.enabled ? 1 : 0.5).disabled(!draft.enabled)
            HStack(spacing:8) { Image(systemName:"lock"); Text("保存在此设备，适用于各工作区。不会从文档或对话自动提取个人记忆。") }.font(.system(size:10)).foregroundStyle(Palette.muted)
            if let error = store.errorMessage { Text(error).font(.system(size:11)).foregroundStyle(Palette.warm) }
            HStack(spacing:18) {
                Button { if store.savePreferences(draft) { dismiss() } } label: { Text("保存到本机").font(.system(size:12,weight:.medium)).foregroundStyle(.white).padding(.horizontal,20).padding(.vertical,11).background(Palette.accent,in:RoundedRectangle(cornerRadius:9)) }.buttonStyle(.plain).disabled(store.contextLocked)
                Button("恢复默认") { draft = PersonalPreferences() }.font(.system(size:11)).buttonStyle(.plain).foregroundStyle(Palette.muted)
                Spacer(); Button("取消") { dismiss() }.font(.system(size:11)).buttonStyle(.plain).foregroundStyle(Palette.muted)
            }
        }.padding(30).frame(width:650).background(Palette.background)
        .onAppear { draft = store.preferences }
        .onChange(of:draft.notes) { _,value in if value.count>600 { draft.notes = String(value.prefix(600)) } }
    }
}
