import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct IslandMark: View {
    var size: CGFloat = 38
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius:size*0.31,style:.continuous).fill(Palette.accent)
            Image(systemName:"mountain.2.fill").font(.system(size:size*0.43,weight:.medium)).foregroundStyle(Color(red:0.92,green:0.96,blue:0.86)).offset(y:-2)
            Capsule().fill(Color.white.opacity(0.6)).frame(width:size*0.39,height:1.4).offset(y:size*0.23)
        }.frame(width:size,height:size)
    }
}

struct RootView: View {
    @EnvironmentObject var store: Store
    var body: some View {
        HStack(spacing:0) {
            Sidebar().frame(width:214)
            Rectangle().fill(Palette.line).frame(width:1)
            VStack(spacing:0) {
                TopBar()
                Rectangle().fill(Palette.line.opacity(0.7)).frame(height:1)
                switch store.page {
                case .workspace: WorkspaceView()
                case .library: if store.activeWorkspace != nil { WorkspaceLibraryView() } else { LibraryView() }
                case .products: WorkProductsView()
                case .privacy: PrivacyView()
                }
            }.frame(maxWidth:.infinity,maxHeight:.infinity)
        }
        .background(Palette.background)
        .foregroundStyle(Palette.ink)
        .overlay(alignment:.bottom) {
            if let message = store.notice {
                HStack(spacing:9) {
                    Image(systemName:"checkmark.circle.fill").foregroundStyle(Palette.accent)
                    Text(message).font(.system(size:12))
                    Button { withAnimation { store.notice = nil } } label: { Image(systemName:"xmark").font(.system(size:10)) }.buttonStyle(.plain)
                }.padding(.horizontal,16).padding(.vertical,11)
                .background(.regularMaterial,in:Capsule()).overlay(Capsule().stroke(Palette.line))
                .shadow(color:.black.opacity(0.06),radius:15,y:4).padding(.bottom,15)
                .transition(.move(edge:.bottom).combined(with:.opacity))
            }
        }
        .environment(\.openURL,OpenURLAction { _ in .discarded })
        .animation(.easeInOut(duration:0.22),value:store.notice)
        .sheet(isPresented:$store.showWelcome) { WelcomeView() }
        .sheet(item:$store.previewArtifact) { ArtifactView(artifact:$0) }
        .sheet(item:$store.previewSource) { SourcePreview(source:$0) }
        .sheet(isPresented:$store.showQueryBuilder) { QueryBuilderView() }
        .sheet(isPresented:$store.showModelLibrary) { ModelLibraryView() }
        .sheet(isPresented:$store.showWorkspacePicker) { WorkspacePickerView() }
        .sheet(isPresented:$store.showPreferences) { PersonalPreferencesView() }
        .alert("清空本地工作记录？",isPresented:$store.showClearConfirmation) {
            Button("取消",role:.cancel) {}
            Button("清空记录与结果",role:.destructive) { store.clearHistory() }
        } message: { Text("会删除归屿保存的对话和生成文件。你选择的原始资料不会删除，文件整理恢复记录会保留。") }
    }
}

struct Sidebar: View {
    @EnvironmentObject var store: Store
    var body: some View {
        VStack(alignment:.leading,spacing:0) {
            HStack(spacing:11) {
                IslandMark()
                VStack(alignment:.leading,spacing:2) {
                    Text("归屿").font(.system(size:22,weight:.semibold,design:.serif)).tracking(3)
                    Text("GUIYU").font(.system(size:8,weight:.medium)).tracking(3).foregroundStyle(Palette.muted)
                }
            }.padding(.horizontal,23).padding(.top,27).padding(.bottom,22)
            WorkspaceSwitcher().padding(.horizontal,16).padding(.bottom,18)
            Button { store.newTask() } label: {
                HStack { Image(systemName:"plus").font(.system(size:14,weight:.medium)); Text("开启新任务").font(.system(size:13,weight:.medium)); Spacer(); Text("⌘ N").font(.system(size:10)).opacity(0.6) }
                    .padding(.horizontal,13).frame(height:40).foregroundStyle(.white).background(Palette.accent,in:RoundedRectangle(cornerRadius:10))
            }.buttonStyle(.plain).padding(.horizontal,17).disabled(store.isBusy)
            VStack(spacing:5) {
                nav(.workspace,"square.grid.2x2")
                nav(.library,"folder")
                nav(.products,"tray.full")
                nav(.privacy,"lock.shield")
            }.padding(.horizontal,12).padding(.top,23)
            HStack { Text("最近的工作").font(.system(size:10,weight:.medium)); Spacer(); Text("仅本机").font(.system(size:9)) }.foregroundStyle(Palette.muted).padding(.horizontal,24).padding(.top,32).padding(.bottom,12)
            if store.history.isEmpty {
                Text("每一次完成，都留在这里。")
                    .font(.system(size:11)).foregroundStyle(Palette.muted.opacity(0.8)).padding(.horizontal,24).padding(.top,4)
            } else {
                ForEach(store.history.prefix(6)) { record in
                    Button { store.openRecord(record) } label: {
                        HStack(spacing:9) {
                            Image(systemName:TaskKind(rawValue:record.kind)?.icon ?? "text.bubble").font(.system(size:11)).foregroundStyle(Palette.muted)
                            Text(record.prompt).font(.system(size:11)).lineLimit(1)
                        }.frame(maxWidth:.infinity,alignment:.leading).padding(.horizontal,13).padding(.vertical,10)
                    }.buttonStyle(.plain).padding(.horizontal,11).disabled(store.isBusy)
                }
            }
            Spacer(minLength:20)
            Button { store.errorMessage = nil; store.showPreferences = true } label: {
                HStack(spacing:9) { Image(systemName:"slider.horizontal.3"); Text("使用习惯"); Spacer(); Text(store.preferences.enabled ? "已开启" : "本机").font(.system(size:9)) }.font(.system(size:11)).foregroundStyle(Palette.muted).padding(.horizontal,24).padding(.vertical,14)
            }.buttonStyle(.plain)
            Button { store.page = .privacy } label: {
                VStack(alignment:.leading,spacing:10) {
                    HStack(spacing:7) {
                        Circle().fill(store.ready ? Palette.accent : Palette.warm).frame(width:6,height:6)
                        Text(store.ready ? "本地空间已就绪" : "正在准备本地空间").font(.system(size:11,weight:.medium))
                        Spacer()
                    }
                    Text(store.ready ? "资料留在此设备，安心做事。" : store.bootMessage).font(.system(size:10)).foregroundStyle(Palette.muted).lineLimit(2)
                }.padding(13).background(Color.white.opacity(0.65),in:RoundedRectangle(cornerRadius:12)).overlay(RoundedRectangle(cornerRadius:12).stroke(Palette.line))
            }.buttonStyle(.plain).padding(.horizontal,16)
            HStack {
                Text("为中文，也为你。").font(.system(size:10)).foregroundStyle(Palette.muted)
                Spacer()
                Button { store.showWelcome = true } label: { Image(systemName:"questionmark.circle").font(.system(size:13)).foregroundStyle(Palette.muted) }.buttonStyle(.plain).help("使用引导")
            }.padding(.horizontal,23).padding(.top,18).padding(.bottom,21)
        }.frame(maxWidth:.infinity,maxHeight:.infinity).background(Palette.sidebar)
    }
    private func nav(_ page: Page,_ icon: String) -> some View {
        Button { withAnimation(.easeInOut(duration:0.15)) { store.page = page } } label: {
            HStack(spacing:11) {
                Image(systemName:icon).font(.system(size:14)).frame(width:19)
                Text(page.rawValue).font(.system(size:12,weight:store.page == page ? .semibold : .regular))
                Spacer()
                if page == .library && (!store.documents.isEmpty || !store.workspaceFiles.isEmpty) { Text("\(store.activeWorkspace == nil ? store.documents.count : store.workspaceFiles.count)").font(.system(size:10)).foregroundStyle(Palette.muted) }
            }.padding(.horizontal,12).frame(height:39)
                .background(store.page == page ? Color.white.opacity(0.85) : .clear,in:RoundedRectangle(cornerRadius:9))
                .foregroundStyle(store.page == page ? Palette.accent : Palette.ink.opacity(0.7))
        }.buttonStyle(.plain)
    }
}

struct TopBar: View {
    @EnvironmentObject var store: Store
    var body: some View {
        HStack(spacing:10) {
            Image(systemName:"square.stack.3d.up").font(.system(size:12)).foregroundStyle(Palette.muted)
            Text(store.workspaceTitle).lineLimit(1).font(.system(size:11)).foregroundStyle(Palette.muted)
            Text("/").font(.system(size:11)).foregroundStyle(Palette.line)
            Text(store.page.rawValue).font(.system(size:11,weight:.medium))
            Spacer()
            Button { store.showModelLibrary = true } label: {
                HStack(spacing:6) { Image(systemName:"cpu"); Text(store.selectedModel?.name ?? "选择本地模型"); Image(systemName:"chevron.down").font(.system(size:8)) }.font(.system(size:10)).foregroundStyle(Palette.accent).padding(.horizontal,10).padding(.vertical,6).background(.white.opacity(0.7),in:Capsule())
            }.buttonStyle(.plain).help("打开本地模型库")
            HStack(spacing:6) { Image(systemName:"lock.fill").font(.system(size:9)); Text(store.networkVerified ? "仅在此设备处理" : "本地空间准备中").font(.system(size:10,weight:.medium)) }
                .foregroundStyle(Palette.accent).padding(.horizontal,11).padding(.vertical,6).background(Palette.pale.opacity(0.65),in:Capsule())
            Button { store.showWelcome = true } label: { Image(systemName:"info.circle").font(.system(size:14)).foregroundStyle(Palette.muted) }.buttonStyle(.plain).padding(.leading,8).help("关于归屿")
        }.padding(.horizontal,28).frame(height:62)
    }
}

struct WorkspaceView: View {
    @EnvironmentObject var store: Store
    var body: some View {
        HStack(spacing:0) {
            VStack(spacing:0) {
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment:.leading,spacing:26) {
                            if store.activePrompt.isEmpty && store.current == nil { if store.isWorkbookDemo { WorkbookShowcaseView() } else if store.isOfficeDemo { OfficeShowcaseView() } else { LandingView() } }
                            else { ConversationView() }
                            Color.clear.frame(height:1).id("bottom")
                        }.padding(.horizontal,36).padding(.top,30).padding(.bottom,18)
                    }.onChange(of:store.step) { _,_ in withAnimation { proxy.scrollTo("bottom",anchor:.bottom) } }
                    .onChange(of:store.isBusy) { _,_ in withAnimation { proxy.scrollTo("bottom",anchor:.bottom) } }
                }
                if let error = store.errorMessage { ErrorBanner(message:error).padding(.horizontal,30).padding(.bottom,10) }
                Composer().padding(.horizontal,30).padding(.bottom,22)
            }.frame(maxWidth:.infinity)
            Rectangle().fill(Palette.line.opacity(0.65)).frame(width:1)
            SourcePanel().frame(width:268)
        }
    }
}

struct LandingView: View {
    @EnvironmentObject var store: Store
    var body: some View {
        VStack(alignment:.leading,spacing:0) {
            HStack(spacing:7) {
                Rectangle().fill(Palette.accent.opacity(0.6)).frame(width:23,height:1)
                Text("YOUR SPACE, YOUR PACE").font(.system(size:9,weight:.medium)).tracking(2.2).foregroundStyle(Palette.muted)
            }.padding(.top,9)
            Text("说出你要做的事，\n归屿一步步完成。")
                .font(.custom("Songti SC",size:37)).lineSpacing(6).foregroundStyle(Palette.ink).padding(.top,23)
            Text("聊想法、解问题、做工作，都留在本机。")
                .font(.system(size:13)).foregroundStyle(Palette.muted).padding(.top,19)
            HStack(spacing:11) {
                TaskCard(kind:.workflow,subtitle:"查找、提取、统计与成稿",accent:Palette.accent)
                TaskCard(kind:.table,subtitle:"从材料到清晰的表格",accent:Color(red:0.56,green:0.45,blue:0.33))
                TaskCard(kind:.write,subtitle:"邮件、通知与文字润色",accent:Color(red:0.39,green:0.48,blue:0.59))
            }.padding(.top,35)
            HStack(spacing:20) {
                quick(.search)
                Button { store.openFilters() } label: { Label("按条件统计",systemImage:"line.3.horizontal.decrease.circle").font(.system(size:11)).foregroundStyle(Palette.accent) }.buttonStyle(.plain).disabled(store.isBusy || !store.ready)
                quick(.compare); quick(.organize)
            }.padding(.top,20)
            Button { store.useSubmissionDemo() } label: {
                HStack(spacing:12) {
                    Image(systemName:"folder.badge.gearshape").font(.system(size:22,weight:.light))
                    VStack(alignment:.leading,spacing:6) { Text("打开归屿演示工作区").font(.system(size:12,weight:.medium));Text("4 份虚构资料 · 工作簿汇总、活动核算、脱敏分享").font(.system(size:10)).foregroundStyle(Palette.muted) }
                    Spacer();Image(systemName:"arrow.up.right")
                }.foregroundStyle(Palette.accent).padding(17).background(Palette.pale.opacity(0.6),in:RoundedRectangle(cornerRadius:12))
            }.buttonStyle(.plain).padding(.top,26).disabled(store.contextLocked)
            Button("体验 18 份日常办公资料 →") { store.openOfficeShowcase() }.font(.system(size:10)).buttonStyle(.plain).foregroundStyle(Palette.muted).padding(.top,13).disabled(store.contextLocked)
            Button("用两份方案快速体验 →") { store.useAdaptiveDemo() }.font(.system(size:10)).buttonStyle(.plain).foregroundStyle(Palette.muted).padding(.top,13)
            Button("体验资料、预算与日期协作 →") { store.useComposedDemo() }.font(.system(size:10)).buttonStyle(.plain).foregroundStyle(Palette.accent).padding(.top,10).disabled(store.contextLocked)
                    Button("体验办公资料 →") { store.useNovelOfficeDemo() }.buttonStyle(.plain).font(.system(size:11)).foregroundStyle(Palette.accent)
                    Button("体验可分享副本 →") { store.useShareDemo() }.buttonStyle(.plain).font(.system(size:11)).foregroundStyle(Palette.accent)
            if !store.documents.isEmpty {
                HStack(spacing:8) {
                    Image(systemName:"checkmark.circle.fill").font(.system(size:12)).foregroundStyle(Palette.accent)
                    Text("\(store.documents.count) 份资料已就位，随时可以开始。")
                        .font(.system(size:11)).foregroundStyle(Palette.muted)
                }.padding(.top,27)
            }
        }.frame(maxWidth:.infinity,alignment:.leading)
    }
    private func quick(_ kind: TaskKind) -> some View {
        Button { store.chooseTemplate(kind) } label: { Label(kind.title,systemImage:kind.icon).font(.system(size:11)).foregroundStyle(Palette.accent) }.buttonStyle(.plain).disabled(store.isBusy)
    }
}

struct TaskCard: View {
    @EnvironmentObject var store: Store
    let kind: TaskKind
    let subtitle: String
    let accent: Color
    @ViewState private var hover = false
    var body: some View {
        Button { store.chooseTemplate(kind) } label: {
            VStack(alignment:.leading,spacing:0) {
                HStack { Image(systemName:kind.icon).font(.system(size:18,weight:.regular)).foregroundStyle(accent).frame(width:35,height:35).background(accent.opacity(0.08),in:RoundedRectangle(cornerRadius:10)); Spacer(); Image(systemName:"arrow.up.right").font(.system(size:10)).foregroundStyle(Palette.muted.opacity(hover ? 1 : 0.4)) }
                Text(kind.title).font(.system(size:13,weight:.medium)).padding(.top,18)
                Text(subtitle).font(.system(size:10)).foregroundStyle(Palette.muted).padding(.top,7).lineLimit(2)
            }.padding(17).frame(maxWidth:.infinity,minHeight:143,alignment:.topLeading)
                .background(Color.white,in:RoundedRectangle(cornerRadius:15))
                .overlay(RoundedRectangle(cornerRadius:15).stroke(hover ? accent.opacity(0.35) : Palette.line.opacity(0.8)))
                .shadow(color:accent.opacity(hover ? 0.07 : 0.01),radius:12,y:4)
                .offset(y:hover ? -2 : 0)
        }.buttonStyle(.plain).onHover { hover = $0 }.animation(.easeOut(duration:0.18),value:hover).disabled(store.isBusy)
    }
}

struct Composer: View {
    @EnvironmentObject var store: Store
    @ViewState private var focused = false
    private var suggestion: String {
        if let record = store.current {
            let tools = record.plan?.steps.map(\.tool) ?? []
            if tools.contains("workbook") { return "继续说：保留条件但换分组、改成前五名、只留这些列…" }
            if tools.contains("compare") { return "继续说：更看重预算，或需要投影仪；也可以把说明改成邮件…" }
            if tools.contains("statistics") || tools.contains("filter") { return "继续问：换一个人呢？也可以改条件、分组，或把结果写成文稿…" }
            if tools.contains("write") { return "继续说：再简短一点、换种语气，或补充你要强调的内容…" }
            return record.sources.isEmpty ? "接着聊，换个问题，或说说下一件想完成的事…" : "继续追问资料，也可以直接聊聊新的想法…"
        }
        if store.activeWorkspace != nil && store.workspaceAutomatic { return "直接提问或说出目标；需要资料时，归屿会自己查找工作区…" }
        return store.documents.isEmpty ? "想从哪里开始？添加资料，或直接说说你的想法…" : "例如：对比这几份方案；找出待办事项；整理成一封邮件…"
    }
    var body: some View {
        VStack(spacing:0) {
            if store.kind != .auto {
                HStack(spacing:6) {
                    Image(systemName:store.kind.icon).font(.system(size:10))
                    Text(store.kind.title).font(.system(size:10,weight:.medium))
                    Button { store.kind = .auto } label: { Image(systemName:"xmark").font(.system(size:8)) }.buttonStyle(.plain)
                    Spacer()
                }.foregroundStyle(Palette.accent).padding(.horizontal,17).padding(.top,14)
            } else {
                HStack(spacing:6) { Image(systemName:"bubble.left.and.bubble.right"); Text(store.current == nil ? "直接交流，需要工具时再安排步骤。" : "接着说，归屿会判断是否需要资料与工具。"); Spacer() }.font(.system(size:10)).foregroundStyle(Palette.muted).padding(.horizontal,17).padding(.top,14)
            }
            ZStack(alignment:.topLeading) {
                if store.prompt.isEmpty { Text(suggestion).font(.system(size:13)).foregroundStyle(Palette.muted.opacity(0.7)).padding(.top,8).padding(.leading,5).allowsHitTesting(false) }
                MessageEditor(text:$store.prompt,focused:$focused,editable:!store.isBusy,canSubmit:store.ready && !store.isBusy && !store.isInspecting && !store.prompt.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,onSubmit:{ store.runTask() }).frame(height:70)
            }.padding(.horizontal,13).padding(.top,8)
            HStack(spacing:10) {
                Button { store.chooseFiles() } label: { Image(systemName:"paperclip").font(.system(size:15)).foregroundStyle(Palette.muted).frame(width:27,height:28) }.buttonStyle(.plain).help("添加资料（⌘O）").disabled(store.isBusy || store.isInspecting)
                if store.activeWorkspace != nil && store.workspaceAutomatic { Text("工作区 · 按需查找").font(.system(size:10)).foregroundStyle(Palette.accent) }
                else if !store.documents.isEmpty { Text("\(store.documents.count) 份资料").font(.system(size:10)).foregroundStyle(Palette.accent).padding(.horizontal,8).padding(.vertical,4).background(Palette.pale,in:Capsule()) }
                if store.current?.plan?.steps.contains(where:{$0.tool=="workbook"}) != true {
                    Button { store.openFilters() } label: { Image(systemName:"line.3.horizontal.decrease.circle").font(.system(size:15)).foregroundStyle(Palette.accent) }.buttonStyle(.plain).help("按条件筛选与分组统计").disabled(store.isBusy || !store.ready || store.documents.isEmpty)
                }
                Menu {
                    Button("交给归屿安排步骤") { store.kind = .auto }
                    Button("直接问答") { store.kind = .answer }
                    Divider()
                    Toggle("执行中检查与调整",isOn:$store.intelligentExecution)
                } label: { Text(store.kind == .answer ? "直接问答" : store.kind.usesPlan ? (store.intelligentExecution ? "智能协作" : "先看计划") : "直接完成").font(.system(size:10)).foregroundStyle(Palette.muted) }.menuStyle(.borderlessButton).fixedSize().disabled(store.isBusy)
                Spacer()
                Text(store.isBusy ? "正在本机处理" : "↵ 发送 · Shift+↵ 换行").font(.system(size:9)).foregroundStyle(Palette.muted.opacity(0.7))
                if store.isBusy {
                    Button { store.cancelTask() } label: { Image(systemName:"stop.fill").font(.system(size:11)).foregroundStyle(Palette.accent).frame(width:33,height:33).background(Palette.pale,in:Circle()) }.buttonStyle(.plain).help("停止任务")
                } else {
                    Button { store.runTask() } label: { Image(systemName:"arrow.up").font(.system(size:14,weight:.semibold)).foregroundStyle(.white).frame(width:33,height:33).background(Palette.accent,in:Circle()) }.buttonStyle(.plain).disabled(!store.ready || store.prompt.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty || store.isInspecting).opacity(store.ready ? 1 : 0.4).help("在本机开始处理")
                }
            }.padding(.horizontal,12).padding(.bottom,12).padding(.top,5)
        }.background(Color.white,in:RoundedRectangle(cornerRadius:18)).overlay(RoundedRectangle(cornerRadius:18).stroke(focused ? Palette.accent.opacity(0.45) : Palette.line)).shadow(color:.black.opacity(0.025),radius:16,y:5)
        .onChange(of:store.kind) { _,_ in focused = true }
    }
}

struct SourcePanel: View {
    @EnvironmentObject var store: Store
    @ViewState private var targeted = false
    var body: some View {
        VStack(alignment:.leading,spacing:0) {
            HStack {
                Text("本次资料").font(.system(size:12,weight:.semibold))
                Spacer()
                if !store.documents.isEmpty { Button { store.removeSources() } label: { Image(systemName:"minus.circle").font(.system(size:12)).foregroundStyle(Palette.muted) }.buttonStyle(.plain).help("取消本次资料授权").disabled(store.isBusy) }
            }.padding(.horizontal,22).padding(.top,29)
            Text(store.activeWorkspace == nil ? "由你选择，由你掌控。" : store.workspaceAutomatic ? "按问题自动选取，本机处理。" : "来自当前工作区的已选文档").font(.system(size:10)).foregroundStyle(Palette.muted).padding(.horizontal,22).padding(.top,9)
            if store.activeWorkspace != nil { WorkspaceIndexCard(compact:true).padding(.horizontal,18).padding(.top,17) }
            Button { if store.activeWorkspace != nil { store.page = .library } else { store.chooseFiles() } } label: {
                VStack(spacing:12) {
                    Image(systemName:"tray.and.arrow.down").font(.system(size:23,weight:.ultraLight)).foregroundStyle(Palette.accent.opacity(0.7))
                    Text(store.isInspecting ? "正在读取资料…" : store.activeWorkspace == nil ? "添加或拖入资料" : "选择工作区文档").font(.system(size:11,weight:.medium))
                    Text("文本 · PDF · Word · Excel").font(.system(size:9)).foregroundStyle(Palette.muted)
                }.frame(maxWidth:.infinity).frame(height:133)
                    .background(targeted ? Palette.pale : Color.white.opacity(0.55),in:RoundedRectangle(cornerRadius:13))
                    .overlay(RoundedRectangle(cornerRadius:13).stroke(style:StrokeStyle(lineWidth:1,dash:[4,4])).foregroundStyle(Palette.line))
            }.buttonStyle(.plain).disabled(store.isBusy || store.isInspecting).padding(.horizontal,19).padding(.top,26)
            .onDrop(of:[UTType.fileURL],isTargeted:$targeted) { providers in
                guard !store.isBusy, !store.isInspecting else { return false }
                let group = DispatchGroup(), lock = NSLock()
                var paths: [String] = []
                for provider in providers {
                    group.enter()
                    _ = provider.loadObject(ofClass:URL.self) { url,_ in
                        if let url { lock.lock(); paths.append(url.path); lock.unlock() }
                        group.leave()
                    }
                }
                group.notify(queue:.main) { store.addPaths(paths) }
                return true
            }
            Button { store.showWorkspacePicker = true } label: { Label(store.activeWorkspace == nil ? "建立文件夹工作区" : "切换文件夹工作区",systemImage:"folder.badge.plus").font(.system(size:10)).foregroundStyle(Palette.muted) }.buttonStyle(.plain).padding(.horizontal,25).padding(.top,13).disabled(store.isBusy)
            ScrollView {
                VStack(spacing:9) {
                    ForEach(store.documents) { source in SourceRow(source:source) }
                    ForEach(Array(store.skippedMessages.enumerated()),id:\.offset) { _, message in Text(message).font(.system(size:10)).foregroundStyle(Palette.warm).frame(maxWidth:.infinity,alignment:.leading).padding(9) }
                }.padding(.horizontal,18).padding(.top,24)
            }
            Spacer(minLength:12)
            VStack(alignment:.leading,spacing:9) {
                Image(systemName:"leaf").font(.system(size:17,weight:.light)).foregroundStyle(Palette.accent.opacity(0.6))
                Text("给资料一个安心的位置。")
                    .font(.custom("Songti SC",size:16)).foregroundStyle(Palette.accent)
                Text(store.activeWorkspace != nil && store.workspaceAutomatic ? "只在已授权的工作区读取。\n按问题选取资料，并保留出处。" : "只读取你选中的内容。\n任务完成，资料仍属于你。")
                    .font(.system(size:10)).lineSpacing(5).foregroundStyle(Palette.muted)
            }.padding(19).frame(maxWidth:.infinity,alignment:.leading).background(Palette.sidebar.opacity(0.45),in:RoundedRectangle(cornerRadius:13)).padding(18)
        }.background(Color.white.opacity(0.3))
    }
}

struct SourceRow: View {
    @EnvironmentObject var store: Store
    let source: SourceDoc
    var body: some View {
        Button { store.previewSource = source } label: {
            HStack(alignment:.top,spacing:10) {
                Image(systemName:source.icon).font(.system(size:16,weight:.light)).foregroundStyle(Palette.accent).frame(width:29,height:33).background(Palette.pale.opacity(0.5),in:RoundedRectangle(cornerRadius:7))
                VStack(alignment:.leading,spacing:6) {
                    Text(source.name).font(.system(size:11)).lineLimit(2).multilineTextAlignment(.leading)
                    HStack(spacing:4) { Text(source.id); Text("·"); Text(ByteCountFormatter.string(fromByteCount:Int64(source.bytes),countStyle:.file)) }.font(.system(size:9)).foregroundStyle(Palette.muted)
                }
                Spacer(minLength:0)
            }.padding(10).background(.white,in:RoundedRectangle(cornerRadius:10)).overlay(RoundedRectangle(cornerRadius:10).stroke(Palette.line.opacity(0.7)))
        }.buttonStyle(.plain)
    }
}

struct ConversationView: View {
    @EnvironmentObject var store: Store
    private var toolCalls: [LocalToolCall] { store.displayedToolCalls }
    private func responseText(_ record: TaskRecord) -> String {
        if record.searchHits?.isEmpty == false, record.plan?.steps.filter({$0.enabled}).allSatisfy({$0.tool == "search"}) == true {
            return record.text.components(separatedBy:"\n").filter { $0.hasPrefix("# 查找") || $0.hasPrefix("匹配 ") || $0.hasPrefix("部分长资料") }.joined(separator:"\n\n")
        }
        if record.plan == nil && record.transaction?.state == "applied" { return "本次资料已整理完成。你可以查看新位置，或撤销本次整理。" }
        if record.plan == nil && record.transaction?.state == "undone" { return "本次整理已撤销，文件已回到原位置。" }
        return record.displayText
    }
    var body: some View {
        VStack(alignment:.leading,spacing:25) {
            if !store.previousTurns.isEmpty {
                VStack(alignment:.leading,spacing:10) {
                    Text("这次对话 · 已有\(store.previousTurns.count)轮").font(.system(size:10,weight:.medium)).foregroundStyle(Palette.muted)
                    ForEach(store.previousTurns) { PreviousTurnView(record:$0) }
                }
            }
            HStack { Spacer(minLength:30); Text(store.activePrompt).font(.system(size:13)).lineSpacing(6).textSelection(.enabled).padding(18).background(Palette.pale.opacity(0.7),in:RoundedRectangle(cornerRadius:15)).frame(maxWidth:650,alignment:.trailing) }
            HStack(alignment:.top,spacing:12) {
                IslandMark(size:29)
                VStack(alignment:.leading,spacing:15) {
                    HStack { Text("归屿").font(.system(size:12,weight:.semibold)); Text("在你的电脑上").font(.system(size:9)).foregroundStyle(Palette.muted) }.padding(.top,5)
                    if store.isBusy && (store.agentPlan == nil || store.isPlanning) { TaskProgress() }
                    if let evidence = store.agentPlan?.retrieval ?? store.retrievalEvidence { RetrievalEvidenceView(evidence:evidence) }
                    if let plan = store.agentPlan { AgentPlanView(plan:plan).id(plan.id) }
                    if !toolCalls.isEmpty { LocalToolTraceView(calls:toolCalls) }
                    if let record = store.current {
                        if record.kind == "chat" {
                            Label(toolCalls.isEmpty ? "直接交流 · 本轮未读取资料" : "本地工具核对 · 本轮未读取资料",systemImage:toolCalls.isEmpty ? "bubble.left" : "checkmark.seal").font(.system(size:10)).foregroundStyle(Palette.muted)
                        }
                        if let summary = record.querySummary, !summary.isEmpty {
                            HStack(alignment:.top,spacing:8) { Image(systemName:"line.3.horizontal.decrease.circle"); Text(summary).lineSpacing(4); Spacer() }.font(.system(size:10)).foregroundStyle(Palette.accent).padding(12).background(Palette.pale.opacity(0.65),in:RoundedRectangle(cornerRadius:10))
                        }
                        if let check=record.shareCheck { ShareDeliveryView(check:check) }
                        MarkdownText(text:responseText(record))
                        if record.displayText != record.text {
                            DisclosureGroup("查看原文与中间结果") { MarkdownText(text:record.text).padding(.top,10) }.font(.system(size:10)).foregroundStyle(Palette.muted)
                        } else if let hits = record.searchHits, !hits.isEmpty { SearchResultsView(hits:hits) }
                        if !record.artifacts.isEmpty { ForEach(record.artifacts) { artifact in ArtifactCard(artifact:artifact) } }
                        if let transaction = record.transaction { TransactionCard(transaction:transaction) }
                        if !record.sources.isEmpty {
                            VStack(alignment:.leading,spacing:9) {
                                Text("参考了这些资料").font(.system(size:10)).foregroundStyle(Palette.muted)
                                ForEach(record.sources) { source in
                                    Button { store.previewSource = source } label: { HStack(spacing:7) { Text(source.id).font(.system(size:9,weight:.semibold)).padding(.horizontal,5).padding(.vertical,3).background(Palette.pale,in:RoundedRectangle(cornerRadius:4)); Text(source.name).font(.system(size:11)); Image(systemName:"arrow.up.right").font(.system(size:8)) }.foregroundStyle(Palette.accent) }.buttonStyle(.plain)
                                }
                            }.padding(.top,6)
                        }
                        HStack(spacing:11) {
                            Text("\(record.plan != nil && record.plan?.state != "completed" ? "已保存进度" : "本机完成") · \(record.seconds,specifier:"%.1f") 秒").font(.system(size:9)).foregroundStyle(Palette.muted)
                            Spacer()
                            Button { store.copy(record.text) } label: { Label("复制",systemImage:"doc.on.doc").font(.system(size:10)).foregroundStyle(Palette.muted) }.buttonStyle(.plain)
                        }.padding(.top,8)
                        if !store.isBusy && record.plan?.state == "completed" {
                            HStack(spacing:10) {
                                if record.plan?.steps.contains(where:{$0.tool=="workbook"}) == true {
                                    Button("从原始数据重新开始") { store.followUp("从原始数据重新开始，取消上轮筛选和排名，导出全部数据。") }
                                } else if record.plan?.steps.contains(where:{["table","filter","statistics"].contains($0.tool)}) == true || record.plan?.reusedTable == true {
                                    Button("调整筛选与分组") { store.openFilters() }.disabled(record.sources.isEmpty)
                                    Button("清除筛选") { store.followUp("清除筛选，统计全部记录。") }.disabled(record.querySummary == nil || record.querySummary?.isEmpty == true)
                                } else { Button("改写为邮件") { store.followUp("把本轮结果改写为一封简短中文邮件，保留事实、数字与出处，缺失信息留待补充。") } }
                                Button("写成简短说明") { store.followUp("把本轮结果写成一段简短说明，保留条件与资料出处。") }
                                Button("查看工作成果") { store.page = .products }.disabled(record.artifacts.isEmpty)
                            }.font(.system(size:10)).buttonStyle(.plain).foregroundStyle(Palette.accent).padding(.top,6)
                        }
                    } else if !store.streamed.isEmpty { MarkdownText(text:store.streamed) }
                }.frame(maxWidth:.infinity,alignment:.leading)
            }
        }
    }
}

struct TaskProgress: View {
    @EnvironmentObject var store: Store
    private var titles:[String] { ["理解需求",store.responseMode == "task" ? "安排步骤" : "读取资料","本地处理","检查结果"] }
    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            if !["chat","clarify","routing","tools"].contains(store.responseMode) { HStack(spacing:0) {
                ForEach(0..<4) { index in
                    HStack(spacing:6) {
                        ZStack {
                            Circle().fill(index <= store.step ? Palette.accent : Palette.line).frame(width:17,height:17)
                            if index < store.step { Image(systemName:"checkmark").font(.system(size:8,weight:.semibold)).foregroundStyle(.white) }
                            else if index == store.step { Circle().fill(.white).frame(width:5,height:5) }
                            else { Text("\(index+1)").font(.system(size:8)).foregroundStyle(Palette.muted) }
                        }
                        Text(titles[index]).font(.system(size:9)).foregroundStyle(index <= store.step ? Palette.accent : Palette.muted)
                    }
                    if index < 3 { Rectangle().fill(Palette.line).frame(height:1).padding(.horizontal,7) }
                }
            } }
            HStack(spacing:8) {
                ProgressView().controlSize(.mini)
                Text(store.progressDetail).font(.system(size:11)).foregroundStyle(Palette.muted)
                Spacer()
                Text("\(Int(store.elapsed))s").font(.system(size:10,design:.monospaced)).foregroundStyle(Palette.muted)
            }
        }.padding(16).background(.white,in:RoundedRectangle(cornerRadius:12)).overlay(RoundedRectangle(cornerRadius:12).stroke(Palette.line))
    }
}

struct MarkdownText: View {
    let text: String
    private var blocks: [[String]] {
        var result: [[String]] = []
        for line in text.components(separatedBy:"\n") {
            if line.trimmingCharacters(in:.whitespaces).hasPrefix("|"), result.last?.first?.trimmingCharacters(in:.whitespaces).hasPrefix("|") == true {
                result[result.count-1].append(line)
            } else if !line.isEmpty { result.append([line]) }
        }
        return result
    }
    private func cells(_ line: String) -> [String] {
        line.trimmingCharacters(in:CharacterSet(charactersIn:" |\t")).components(separatedBy:"|").map { $0.trimmingCharacters(in:.whitespaces) }
    }
    var body: some View {
        VStack(alignment:.leading,spacing:11) {
            ForEach(Array(blocks.enumerated()),id:\.offset) { _, block in
                if block.count > 1 && block[0].trimmingCharacters(in:.whitespaces).hasPrefix("|") {
                    ScrollView(.horizontal) {
                        VStack(alignment:.leading,spacing:0) {
                            ForEach(Array(block.filter { !cells($0).allSatisfy { $0.replacingOccurrences(of:":",with:"").trimmingCharacters(in:CharacterSet(charactersIn:"- ")).isEmpty } }.enumerated()),id:\.offset) { index, row in
                                HStack(alignment:.top,spacing:0) {
                                    ForEach(Array(cells(row).enumerated()),id:\.offset) { _, cell in
                                        Text((try? AttributedString(markdown:cell)) ?? AttributedString(cell)).font(.system(size:11,weight:index == 0 ? .semibold : .regular)).textSelection(.enabled).frame(width:135,alignment:.leading).padding(10)
                                    }
                                }.background(index == 0 ? Palette.pale : Color.white)
                                Rectangle().fill(Palette.line).frame(height:1)
                            }
                        }
                    }.clipShape(RoundedRectangle(cornerRadius:9))
                } else if let line = block.first {
                    if line.hasPrefix("#") { Text(line.trimmingCharacters(in:CharacterSet(charactersIn:"# "))).font(.system(size:line.hasPrefix("###") ? 13 : 16,weight:.semibold)).padding(.top,8).textSelection(.enabled) }
                    else { Text((try? AttributedString(markdown:line)) ?? AttributedString(line)).font(.system(size:12)).lineSpacing(6).textSelection(.enabled).frame(maxWidth:.infinity,alignment:.leading) }
                }
            }
        }
    }
}

struct ArtifactCard: View {
    @EnvironmentObject var store: Store
    let artifact: Artifact
    var body: some View {
        Button { store.previewArtifact = artifact } label: {
            HStack(spacing:13) {
                Image(systemName:["xlsx","csv"].contains(artifact.type) ? "tablecells" : "doc.text").font(.system(size:24,weight:.light)).foregroundStyle(Palette.accent).frame(width:48,height:54).background(Palette.pale.opacity(0.6),in:RoundedRectangle(cornerRadius:10))
                VStack(alignment:.leading,spacing:7) {
                    Text(artifact.name).font(.system(size:12,weight:.medium))
                    Text(["xlsx","csv"].contains(artifact.type) ? "可编辑表格 · 已保存到本机" : "可编辑文稿 · 已保存到本机").font(.system(size:10)).foregroundStyle(Palette.muted)
                }
                Spacer()
                Text("预览").font(.system(size:11)).foregroundStyle(Palette.accent)
                Image(systemName:"arrow.up.right").font(.system(size:10)).foregroundStyle(Palette.accent)
            }.padding(14).background(.white,in:RoundedRectangle(cornerRadius:13)).overlay(RoundedRectangle(cornerRadius:13).stroke(Palette.line))
        }.buttonStyle(.plain)
    }
}

struct TransactionCard: View {
    @EnvironmentObject var store: Store
    let transaction: FileTransaction
    var body: some View {
        VStack(alignment:.leading,spacing:14) {
            HStack { Label("整理预览",systemImage:"folder.badge.gearshape").font(.system(size:12,weight:.semibold)); Spacer(); Text(transaction.state == "preview" ? "原文件未改动" : transaction.state == "undone" ? "已撤销" : "已整理").font(.system(size:10)).foregroundStyle(Palette.accent) }
            ForEach(transaction.moves) { move in
                VStack(alignment:.leading,spacing:6) {
                    Text(move.name).font(.system(size:10)).foregroundStyle(Palette.muted)
                    Label("\(move.category) / \(move.newName)",systemImage:"arrow.turn.down.right").font(.system(size:11)).foregroundStyle(Palette.ink)
                }.padding(.vertical,5)
            }
            if transaction.state == "preview" {
                Button { store.applyTransaction() } label: { Label(store.isApplying ? "正在整理…" : "确认，开始整理",systemImage:"checkmark").font(.system(size:11,weight:.medium)).foregroundStyle(.white).padding(.horizontal,14).padding(.vertical,9).background(Palette.accent,in:RoundedRectangle(cornerRadius:8)) }.buttonStyle(.plain).disabled(store.isApplying)
            } else if transaction.state == "applied" || transaction.state == "applying" {
                Button { store.undoTransaction() } label: { Label("撤销本次整理",systemImage:"arrow.uturn.backward").font(.system(size:11,weight:.medium)).foregroundStyle(Palette.accent).padding(.horizontal,14).padding(.vertical,9).background(Palette.pale,in:RoundedRectangle(cornerRadius:8)) }.buttonStyle(.plain).disabled(store.isApplying)
            }
        }.padding(17).background(.white,in:RoundedRectangle(cornerRadius:13)).overlay(RoundedRectangle(cornerRadius:13).stroke(Palette.line))
    }
}

struct LibraryView: View {
    @EnvironmentObject var store: Store
    var body: some View {
        ScrollView {
            VStack(alignment:.leading,spacing:25) {
                Text("你的资料，你来选择。").font(.custom("Songti SC",size:32))
                Text("添加本次任务需要的内容。归屿只在此设备读取，不会自动扫描整台电脑。")
                    .font(.system(size:12)).foregroundStyle(Palette.muted)
                HStack(spacing:12) {
                    Button { store.chooseFiles() } label: { Label("添加资料",systemImage:"plus").padding(.horizontal,16).padding(.vertical,10).background(Palette.accent,in:RoundedRectangle(cornerRadius:9)).foregroundStyle(.white) }.buttonStyle(.plain)
                    Button("选择文件夹") { store.chooseFiles(folder:true) }.buttonStyle(.plain).foregroundStyle(Palette.accent)
                    Spacer()
                    Button("使用示例") { store.useDemo() }.buttonStyle(.plain).foregroundStyle(Palette.muted)
                }.font(.system(size:12))
                if store.documents.isEmpty {
                    VStack(spacing:15) { Image(systemName:"folder.badge.plus").font(.system(size:40,weight:.ultraLight)); Text("留一点位置，给接下来的灵感。").font(.custom("Songti SC",size:20)); Text("支持 TXT、Markdown、PDF、Word、Excel 和 CSV").font(.system(size:11)) }.foregroundStyle(Palette.muted).frame(maxWidth:.infinity).frame(height:280).card()
                } else {
                    LazyVGrid(columns:[GridItem(.adaptive(minimum:260))],spacing:15) { ForEach(store.documents) { SourceRow(source:$0) } }
                    Button("取消本次资料授权") { store.removeSources() }.font(.system(size:11)).buttonStyle(.plain).foregroundStyle(Palette.muted)
                }
            }.padding(40)
        }
    }
}

struct PrivacyView: View {
    @EnvironmentObject var store: Store
    var body: some View {
        ScrollView {
            VStack(alignment:.leading,spacing:24) {
                HStack(alignment:.top) {
                    VStack(alignment:.leading,spacing:13) {
                        Text("安心，是默认的。") .font(.custom("Songti SC",size:34))
                        Text("从选择资料到拿到结果，这个空间属于你。").font(.system(size:12)).foregroundStyle(Palette.muted)
                    }
                    Spacer()
                    Image(systemName:"lock.shield").font(.system(size:42,weight:.ultraLight)).foregroundStyle(Palette.accent.opacity(0.65))
                }.padding(.bottom,8)
                HStack(spacing:15) {
                    privacyCard("处理留在本机","模型、资料与工具在此设备运行。","desktopcomputer",store.ready ? "本地模型已就绪" : store.bootMessage)
                    privacyCard("网络连接已隔离","应用与处理进程禁用网络连接。","network.slash",store.networkVerified ? "运行时检查已确认" : "等待运行时确认")
                    privacyCard("资料范围由你定","只使用你为本次任务选择的资料。","folder.badge.person.crop",store.documents.isEmpty ? "尚未添加资料" : "已选择 \(store.documents.count) 份资料")
                }
                PrivacyRedactionView()
                VStack(alignment:.leading,spacing:19) {
                    Text("本地空间").font(.system(size:14,weight:.semibold))
                    infoRow("资料处理","本地运行，不调用云端模型")
                    infoRow("对话与工作记录","保存在此设备，可导出或清空")
                    infoRow("使用统计与自动上传","未启用")
                    infoRow("模型下载","独立组件，仅接收模型编号")
                    infoRow("当前工作区",store.workspaceTitle)
                    infoRow("当前模型",store.ready ? store.loadedModelName : "尚未就绪")
                    Button("选择或添加本地模型") { store.showModelLibrary = true }.font(.system(size:11)).buttonStyle(.plain).foregroundStyle(Palette.accent)
                    Divider().overlay(Palette.line)
                    HStack(spacing:22) {
                        Button { store.exportHistory() } label: { Label("导出工作记录",systemImage:"square.and.arrow.up") }
                        Button { store.revealStorage() } label: { Label("打开本机存储",systemImage:"folder") }
                        Spacer()
                        Button("清空记录与结果") { store.showClearConfirmation = true }.foregroundStyle(Palette.warm)
                    }.font(.system(size:11)).buttonStyle(.plain).foregroundStyle(Palette.accent)
                }.padding(24).card()
                if !store.ready {
                    HStack { Text(store.bootMessage).font(.system(size:12)); Spacer(); Button("重新连接本地引擎") { store.startWorker() }.buttonStyle(.plain).foregroundStyle(Palette.accent) }.padding(18).card()
                }
                VStack(alignment:.leading,spacing:9) {
                    Text("关于这个边界").font(.system(size:11,weight:.medium))
                    Text("归屿的禁网隔离覆盖应用和本地处理进程。模型下载使用独立联网组件，它的文件访问限制在模型目录和必要系统资源，无法读取工作区与对话记录。你主动用其他软件打开或导出结果后，由所选软件和保存位置决定后续处理方式。扫描件识别、联网搜索和任意电脑操作不在此 Demo 的支持范围内。")
                        .font(.system(size:10)).foregroundStyle(Palette.muted).lineSpacing(5)
                }.padding(.horizontal,4)
                if let error = store.errorMessage { ErrorBanner(message:error) }
            }.padding(40)
        }
    }
    private func infoRow(_ title:String,_ value:String)->some View { HStack { Text(title).font(.system(size:11)).foregroundStyle(Palette.muted); Spacer(); Text(value).font(.system(size:11)) } }
    private func privacyCard(_ title:String,_ subtitle:String,_ icon:String,_ status:String)->some View {
        VStack(alignment:.leading,spacing:13) {
            Image(systemName:icon).font(.system(size:23,weight:.light)).foregroundStyle(Palette.accent).frame(height:30)
            Text(title).font(.system(size:13,weight:.medium))
            Text(subtitle).font(.system(size:10)).foregroundStyle(Palette.muted).lineSpacing(4).frame(minHeight:32,alignment:.topLeading)
            Text(status).font(.system(size:9,weight:.medium)).foregroundStyle(Palette.accent).padding(.top,3)
        }.frame(maxWidth:.infinity,alignment:.leading).padding(21).card()
    }
}

struct WelcomeView: View {
    @EnvironmentObject var store: Store
    var body: some View {
        VStack(alignment:.leading,spacing:0) {
            HStack { IslandMark(size:49); Spacer(); Text("你好，欢迎来到归屿").font(.system(size:11)).foregroundStyle(Palette.muted) }
            Text("把事情交给助手，\n把资料留给自己。")
                .font(.custom("Songti SC",size:33)).lineSpacing(8).padding(.top,30)
            Text("用中文说出需求，在自己的电脑上完成。")
                .font(.system(size:13)).foregroundStyle(Palette.muted).padding(.top,17)
            HStack(alignment:.top,spacing:22) {
                welcomeStep("1","选好资料","添加文件或文件夹")
                welcomeStep("2","说出想法","用你熟悉的中文表达")
                welcomeStep("3","拿到结果","预览、保存，也能撤销整理")
            }.padding(.top,33)
            HStack(spacing:7) { Image(systemName:"lock.fill"); Text("资料在本机处理，没有自动上传。") }.font(.system(size:10)).foregroundStyle(Palette.accent).padding(.top,32)
            HStack(spacing:18) {
                Button { store.dismissWelcome() } label: { HStack { Text("开启我的本地空间"); Image(systemName:"arrow.right") }.font(.system(size:12,weight:.medium)).foregroundStyle(.white).padding(.horizontal,20).padding(.vertical,12).background(Palette.accent,in:RoundedRectangle(cornerRadius:10)) }.buttonStyle(.plain)
                Button("先用办公样例体验") { store.dismissWelcome(); store.openOfficeShowcase() }.font(.system(size:11)).buttonStyle(.plain).foregroundStyle(Palette.accent)
                Spacer()
            }.padding(.top,24)
        }.padding(39).frame(width:650).background(Palette.background)
    }
    private func welcomeStep(_ number:String,_ title:String,_ text:String)->some View {
        VStack(alignment:.leading,spacing:9) { Text(number).font(.system(size:11,weight:.medium)).foregroundStyle(Palette.accent).frame(width:25,height:25).background(Palette.pale,in:Circle()); Text(title).font(.system(size:12,weight:.medium)); Text(text).font(.system(size:10)).foregroundStyle(Palette.muted) }.frame(maxWidth:.infinity,alignment:.leading)
    }
}

struct ArtifactView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) var dismiss
    let artifact: Artifact
    var body: some View {
        VStack(alignment:.leading,spacing:20) {
            HStack {
                Label(artifact.name,systemImage:["xlsx","csv"].contains(artifact.type) ? "tablecells" : "doc.text").font(.system(size:16,weight:.semibold))
                Spacer(); Button { dismiss() } label: { Image(systemName:"xmark.circle.fill").foregroundStyle(Palette.muted) }.buttonStyle(.plain)
            }
            Text("生成时预览 · 文件保存在本机，可另存副本继续编辑").font(.system(size:11)).foregroundStyle(Palette.muted)
            if artifact.type == "xlsx" {
                ScrollView([.horizontal,.vertical]) {
                    VStack(alignment:.leading,spacing:0) {
                        tableLine(artifact.columns ?? store.current?.columns ?? [],header:true)
                        ForEach(Array((artifact.rows ?? store.current?.rows ?? []).enumerated()),id:\.offset) { _, row in tableLine(row,header:false) }
                    }
                }.frame(minHeight:220,maxHeight:420).background(.white,in:RoundedRectangle(cornerRadius:10))
            } else {
                ScrollView { MarkdownText(text:artifact.preview ?? store.current?.text ?? "").padding(24).frame(maxWidth:.infinity,alignment:.leading) }.frame(minHeight:250,maxHeight:420).background(.white,in:RoundedRectangle(cornerRadius:10))
            }
            HStack(spacing:20) {
                Button { store.openArtifact(artifact) } label: { Label("用本机应用打开",systemImage:"arrow.up.right.square").padding(.horizontal,16).padding(.vertical,10).background(Palette.accent,in:RoundedRectangle(cornerRadius:9)).foregroundStyle(.white) }.buttonStyle(.plain)
                Button { store.revealArtifact(artifact) } label: { Label("在访达中显示",systemImage:"folder") }.buttonStyle(.plain).foregroundStyle(Palette.accent)
                Button { store.saveArtifactCopy(artifact) } label: { Label("保存副本",systemImage:"square.and.arrow.up") }.buttonStyle(.plain).foregroundStyle(Palette.accent)
                Spacer()
            }.font(.system(size:11))
        }.padding(28).frame(width:780).background(Palette.background)
    }
    private func tableLine(_ values:[String],header:Bool)->some View {
        HStack(alignment:.top,spacing:0) { ForEach(Array(values.enumerated()),id:\.offset) { _, value in Text(value).font(.system(size:11,weight:header ? .semibold : .regular)).textSelection(.enabled).frame(width:150,alignment:.leading).padding(12) } }.background(header ? Palette.pale : .white).overlay(alignment:.bottom) { Rectangle().fill(Palette.line).frame(height:1) }
    }
}

struct SourcePreview: View {
    @Environment(\.dismiss) var dismiss
    let source: SourceDoc
    var body: some View {
        VStack(alignment:.leading,spacing:20) {
            HStack { Label(source.name,systemImage:source.icon).font(.system(size:15,weight:.semibold)); Spacer(); Button { dismiss() } label: { Image(systemName:"xmark.circle.fill").foregroundStyle(Palette.muted) }.buttonStyle(.plain) }
            Text("\(source.id) · 原文开头片段").font(.system(size:11)).foregroundStyle(Palette.muted)
            ScrollView { Text(source.preview.isEmpty ? "此历史记录未保存原文预览。重新选择原文件后可查看。" : source.preview).font(.system(size:13)).lineSpacing(8).textSelection(.enabled).frame(maxWidth:.infinity,alignment:.leading).padding(22) }.frame(height:340).background(.white,in:RoundedRectangle(cornerRadius:12))
            Text("原文件保持在你选择的位置，归屿不自动上传资料。").font(.system(size:10)).foregroundStyle(Palette.muted)
        }.padding(28).frame(width:620).background(Palette.background)
    }
}

struct ErrorBanner: View {
    let message: String
    var body: some View { HStack(alignment:.top,spacing:9) { Image(systemName:"info.circle"); Text(message).lineSpacing(4); Spacer(minLength:0) }.font(.system(size:11)).foregroundStyle(Palette.warm).padding(13).background(Palette.warm.opacity(0.07),in:RoundedRectangle(cornerRadius:10)) }
}

extension View {
    func card()->some View { background(Color.white,in:RoundedRectangle(cornerRadius:14)).overlay(RoundedRectangle(cornerRadius:14).stroke(Palette.line.opacity(0.8))) }
}
