import SwiftUI

struct AgentPlanView: View {
    @EnvironmentObject var store: Store
    let plan: AgentPlan
    @ViewState private var editing = false
    @ViewState private var collapsed = false
    var body: some View {
        VStack(alignment:.leading,spacing:0) {
            HStack(alignment:.center,spacing:10) {
                Image(systemName:plan.state == "completed" ? "checkmark.circle.fill" : "list.bullet.clipboard").font(.system(size:17)).foregroundStyle(Palette.accent)
                VStack(alignment:.leading,spacing:5) {
                    Text(heading).font(.system(size:13,weight:.semibold))
                    Text(subtitle).font(.system(size:10)).foregroundStyle(Palette.muted)
                }
                Spacer(minLength:5)
                if plan.canContinue {
                    Button(editing ? "调整好了" : "调整步骤") { withAnimation { editing.toggle() } }.font(.system(size:10,weight:.medium)).buttonStyle(.plain).foregroundStyle(Palette.accent).disabled(store.isBusy)
                }
                if ["completed","running"].contains(plan.state) {
                    Button { withAnimation { collapsed.toggle() } } label: { Image(systemName:collapsed ? "chevron.down" : "chevron.up").font(.system(size:11)).foregroundStyle(Palette.muted) }.buttonStyle(.plain).help("展开或收起执行步骤")
                }
            }.padding(18)
            if store.isBusy,plan.steps.contains(where:{$0.tool=="share"}) {
                Label(store.progressDetail,systemImage:"lock.shield").font(.system(size:11)).foregroundStyle(Palette.accent).lineSpacing(4).padding(.horizontal,18).padding(.bottom,14)
            }
            if plan.adaptive == true { AgentActivityView(plan:plan).padding(.horizontal,18).padding(.bottom,14) }
            if plan.state == "completed",plan.completionState != "passed",let message=plan.completionMessage {
                Label(message,systemImage:plan.completionState == "passed" ? "checkmark.circle" : "doc.text.magnifyingglass")
                    .font(.system(size:11)).foregroundStyle(plan.completionState == "passed" ? Palette.accent : Palette.warm)
                    .lineSpacing(4).padding(.horizontal,18).padding(.bottom,14)
            }
            if plan.groundedDelivery == true {
                Label("已保留可核对依据，文稿的选择建议与最终结论待确认。",systemImage:"doc.text.magnifyingglass").font(.system(size:11)).foregroundStyle(Palette.warm).lineSpacing(4).padding(.horizontal,18).padding(.bottom,15)
            }
            if plan.state == "needs_input" {
                VStack(alignment:.leading,spacing:12) {
                    Text(plan.error ?? "还需要一点信息。").font(.system(size:12)).lineSpacing(5)
                    Button("补充要求 →") { store.supplementGoal() }.font(.system(size:11,weight:.medium)).buttonStyle(.plain).foregroundStyle(Palette.accent).disabled(store.isBusy)
                }.padding(15).frame(maxWidth:.infinity,alignment:.leading).background(Palette.pale.opacity(0.5),in:RoundedRectangle(cornerRadius:10)).padding(.horizontal,18).padding(.bottom,15)
            }
            if !collapsed,let note = plan.planningNote,!note.isEmpty {
                Text(note).font(.system(size:11)).foregroundStyle(Palette.muted).lineSpacing(5).padding(.horizontal,18).padding(.bottom,13)
            }
            if !collapsed,let summary = plan.preferenceSummary,!summary.isEmpty {
                Label("表达习惯："+summary,systemImage:"slider.horizontal.3").font(.system(size:9)).foregroundStyle(Palette.accent).padding(.horizontal,18).padding(.bottom,13)
            }
            if let summary = plan.querySummary, !summary.isEmpty, !collapsed {
                VStack(alignment:.leading,spacing:6) {
                    Label(summary,systemImage:"line.3.horizontal.decrease.circle").font(.system(size:10)).foregroundStyle(Palette.accent).lineSpacing(4)
                    if plan.reusedTable == true { Text("沿用上轮原始表格，按本轮条件重新计算。").font(.system(size:9)).foregroundStyle(Palette.muted) }
                }.frame(maxWidth:.infinity,alignment:.leading).padding(.horizontal,18).padding(.bottom,15)
            }
            if !collapsed {
                Rectangle().fill(Palette.line).frame(height:1)
                VStack(alignment:.leading,spacing:0) {
                    ForEach(Array(plan.steps.enumerated()),id:\.element.id) { index,step in
                        AgentStepRow(step:step,number:index+1,editing:editing && plan.canContinue)
                        if index < plan.steps.count-1 { Rectangle().fill(Palette.line.opacity(0.55)).frame(height:1).padding(.leading,49) }
                    }
                }.padding(.horizontal,17).padding(.vertical,5)
                if plan.canContinue {
                    Rectangle().fill(Palette.line).frame(height:1)
                    VStack(alignment:.leading,spacing:12) {
                        Text(plan.sourceNames.isEmpty ? "这项任务仅依据你的要求和近期对话。" : "这项任务使用 \(plan.sourceNames.count) 份已选资料。继续时仍使用本次原资料。")
                            .font(.system(size:10)).foregroundStyle(Palette.muted).lineSpacing(4)
                        HStack(spacing:16) {
                            Button { editing = false; store.executePlan() } label: {
                                Label(plan.state == "draft" ? "开始执行 \(plan.pendingCount) 步" : "继续剩余 \(plan.pendingCount) 步",systemImage:"play.fill").font(.system(size:11,weight:.medium)).foregroundStyle(.white).padding(.horizontal,16).padding(.vertical,10).background(Palette.accent,in:RoundedRectangle(cornerRadius:9))
                            }.buttonStyle(.plain).disabled(!store.ready || store.isBusy || plan.pendingCount == 0 || store.isInspecting)
                            Button("重新交代") { store.newTask() }.font(.system(size:10)).buttonStyle(.plain).foregroundStyle(Palette.muted).disabled(store.isBusy)
                            Spacer()
                            if plan.completedCount > 0 { Text("已保留完成结果").font(.system(size:9)).foregroundStyle(Palette.accent) }
                        }
                    }.padding(18)
                }
            }
        }.background(Color.white,in:RoundedRectangle(cornerRadius:15)).overlay(RoundedRectangle(cornerRadius:15).stroke(Palette.line))
        .onChange(of:plan.state) { _,state in if ["completed","running"].contains(state) { withAnimation { collapsed = true } } }
        .onAppear { collapsed = ["completed","running"].contains(plan.state) }
    }
    private var heading: String {
        switch plan.state { case "draft": return "这样安排，可以吗"; case "running": return "正在协作完成"; case "completed": return plan.groundedDelivery == true ? "资料已整理，文稿建议待确认" : "\(plan.completedCount) 个步骤已完成"; case "needs_input": return "还需要你补充一点信息"; case "failed": return "进度已保留，这一步需要调整"; default: return "进度已保留，随时继续" }
    }
    private var subtitle: String {
        switch plan.state { case "running": return "\(plan.completedCount) / \(plan.enabledCount) 步已完成 · 全程本机处理"; case "completed": return "查看每一步的结果和执行记录"; default: return "先理清步骤，再把事情做好。" }
    }
}

struct AgentStepRow: View {
    @EnvironmentObject var store: Store
    let step: AgentStep
    let number: Int
    let editing: Bool
    @ViewState private var expanded = false
    var body: some View {
        VStack(alignment:.leading,spacing:10) {
            HStack(alignment:.top,spacing:12) {
                ZStack {
                    Circle().fill(step.state == "completed" ? Palette.accent : Palette.pale).frame(width:28,height:28)
                    if step.state == "completed" { Image(systemName:"checkmark").font(.system(size:11,weight:.semibold)).foregroundStyle(.white) }
                    else if step.state == "running" { ProgressView().controlSize(.mini) }
                    else { Text("\(number)").font(.system(size:10,weight:.medium)).foregroundStyle(Palette.accent) }
                }
                VStack(alignment:.leading,spacing:6) {
                    HStack(spacing:7) {
                        Image(systemName:step.icon).font(.system(size:11)).foregroundStyle(Palette.accent)
                        Text(step.title).font(.system(size:12,weight:.medium)).strikethrough(!step.enabled).foregroundStyle(step.enabled ? Palette.ink : Palette.muted)
                        if step.adaptiveAdded == true { Text("补充步骤").font(.system(size:8)).foregroundStyle(Palette.accent) }
                        if step.effect == "preview" { Text("先给方案").font(.system(size:8)).foregroundStyle(Palette.accent) }
                        Spacer()
                        if editing && step.state != "completed" {
                            Toggle("执行",isOn:Binding(get:{step.enabled},set:{store.updatePlanStep(step.id,enabled:$0)})).toggleStyle(.checkbox).font(.system(size:10))
                        } else if step.state == "completed" {
                            Text("\(step.seconds,specifier:"%.1f") 秒").font(.system(size:9)).foregroundStyle(Palette.muted)
                        } else if step.state == "running" { Text("进行中").font(.system(size:9)).foregroundStyle(Palette.accent) }
                    }
                    Text(step.summary.isEmpty ? (step.instruction.isEmpty ? step.detail : String(step.instruction.prefix(160))) : step.summary).font(.system(size:10)).foregroundStyle(step.state == "failed" ? Palette.warm : Palette.muted).lineSpacing(4).fixedSize(horizontal:false,vertical:true)
                    if let checked = step.checkMessage { Label(checked,systemImage:"checkmark.shield").font(.system(size:9)).foregroundStyle(Palette.accent) }
                    if !step.output.isEmpty {
                        Button(expanded ? "收起结果" : "查看这一步") { withAnimation { expanded.toggle() } }.font(.system(size:9)).buttonStyle(.plain).foregroundStyle(Palette.accent)
                    }
                }.padding(.top,2)
            }
            if editing && step.state != "completed" {
                TextEditor(text:Binding(get:{step.instruction},set:{store.updatePlanStep(step.id,instruction:$0)}))
                    .font(.system(size:11)).scrollContentBackground(.hidden).frame(height:58).padding(8).background(Palette.background,in:RoundedRectangle(cornerRadius:8)).overlay(RoundedRectangle(cornerRadius:8).stroke(Palette.line)).padding(.leading,40).disabled(!step.enabled)
            }
            if expanded { MarkdownText(text:step.output).padding(13).background(Palette.background,in:RoundedRectangle(cornerRadius:8)).padding(.leading,40) }
        }.padding(.vertical,13)
    }
}

struct AgentActivityView: View {
    let plan: AgentPlan
    @ViewState private var expanded = false
    private var events:[AgentActivity] { plan.events ?? [] }
    var body:some View {
        VStack(alignment:.leading,spacing:10) {
            Button { withAnimation { expanded.toggle() } } label: {
                HStack(spacing:8) {
                    Image(systemName:"sparkles").foregroundStyle(Palette.accent)
                    Text(plan.state == "draft" ? "智能协作 · 执行中检查与调整" : events.last?.message ?? "智能协作").font(.system(size:10)).lineLimit(2).multilineTextAlignment(.leading)
                    Spacer(minLength:5)
                    Image(systemName:expanded ? "chevron.up" : "chevron.down").font(.system(size:8))
                }.foregroundStyle(Palette.accent)
            }.buttonStyle(.plain)
            if expanded {
                ForEach(events.suffix(8)) { item in
                    HStack(alignment:.top,spacing:9) {
                        Circle().fill(item.kind == "waiting" ? Palette.warm : Palette.accent.opacity(0.5)).frame(width:5,height:5).padding(.top,4)
                        Text(item.message).font(.system(size:10)).foregroundStyle(Palette.muted).lineSpacing(4)
                    }
                }
                Text("检查覆盖输出结构、原文引用和文件状态，重要结论仍可按出处核对。").font(.system(size:9)).foregroundStyle(Palette.muted).lineSpacing(3)
            }
        }.padding(12).background(Palette.pale.opacity(0.6),in:RoundedRectangle(cornerRadius:10))
    }
}
