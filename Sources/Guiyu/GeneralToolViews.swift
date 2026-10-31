import SwiftUI

struct LocalToolTraceView: View {
    let calls: [LocalToolCall]
    @ViewState private var expanded = false

    private var isRunning: Bool { calls.contains { $0.state == "running" } }
    private var hasFailure: Bool { calls.contains { $0.state == "failed" } }
    private var overview: String {
        if isRunning { return "正在核对" }
        return hasFailure ? "有项目需要确认" : "已核对 \(calls.count) 项"
    }

    var body: some View {
        VStack(alignment:.leading,spacing:0) {
            Button {
                withAnimation(.easeInOut(duration:0.18)) { expanded.toggle() }
            } label: {
                HStack(spacing:8) {
                    Image(systemName:"checkmark.seal").font(.system(size:12)).foregroundStyle(Palette.accent)
                    Text("本地工具核对").font(.system(size:11,weight:.medium)).foregroundStyle(Palette.ink)
                    Text(overview).font(.system(size:9)).foregroundStyle(Palette.muted)
                    Spacer(minLength:8)
                    Image(systemName:"lock").font(.system(size:8)).foregroundStyle(Palette.muted)
                    Text("全部在本机").font(.system(size:9)).foregroundStyle(Palette.muted)
                    Image(systemName:expanded ? "chevron.up" : "chevron.down").font(.system(size:8,weight:.medium)).foregroundStyle(Palette.muted).padding(.leading,3)
                }.contentShape(Rectangle()).padding(.horizontal,14).padding(.vertical,12)
            }.buttonStyle(.plain).help(expanded ? "收起核对详情" : "查看计算内容与核对结果")
            VStack(alignment:.leading,spacing:12) {
                ForEach(expanded ? calls : Array(calls.suffix(3)),id:\.id) { call in
                    VStack(alignment:.leading,spacing:7) {
                        HStack(alignment:.top,spacing:8) {
                            statusIcon(call).frame(width:15,height:15)
                            VStack(alignment:.leading,spacing:5) {
                                Text(call.title.isEmpty ? toolTitle(call) : call.title).font(.system(size:10,weight:.medium)).foregroundStyle(Palette.ink)
                                if !call.summary.isEmpty {
                                    Text(call.summary).font(.system(size:11)).foregroundStyle(Palette.accent).lineSpacing(4).textSelection(.enabled)
                                }
                            }
                            Spacer(minLength:4)
                            Text(statusText(call)).font(.system(size:9)).foregroundStyle(call.state == "failed" ? Palette.warm : Palette.muted)
                        }
                        if expanded {
                            VStack(alignment:.leading,spacing:10) {
                                if !call.input.isEmpty { detail(["calculate","calculator"].contains(call.tool) ? "计算内容" : "核对内容",text:call.input) }
                                if !call.output.isEmpty { detail("核对结果",text:call.output) }
                            }.padding(11).frame(maxWidth:.infinity,alignment:.leading)
                                .background(Color.white.opacity(0.7),in:RoundedRectangle(cornerRadius:8))
                                .padding(.leading,23)
                        }
                    }
                }
                if !expanded && calls.count > 3 {
                    Text("展开查看全部 \(calls.count) 项处理").font(.system(size:9)).foregroundStyle(Palette.muted).padding(.leading,23)
                }
            }.padding(.horizontal,14).padding(.bottom,13)
        }.background(Palette.pale.opacity(0.45),in:RoundedRectangle(cornerRadius:12))
            .overlay(RoundedRectangle(cornerRadius:12).stroke(Palette.line.opacity(0.8)))
    }

    @ViewBuilder private func statusIcon(_ call: LocalToolCall) -> some View {
        if call.state == "running" { ProgressView().controlSize(.mini) }
        else {
            Image(systemName:call.state == "failed" ? "exclamationmark.circle" : "checkmark.circle.fill")
                .font(.system(size:12)).foregroundStyle(call.state == "failed" ? Palette.warm : Palette.accent)
        }
    }
    private func statusText(_ call: LocalToolCall) -> String {
        switch call.state { case "running": return "核对中"; case "failed": return "未完成"; default: return "已完成" }
    }
    private func toolTitle(_ call: LocalToolCall) -> String {
        ["calculate","calculator"].contains(call.tool) ? "计算" : "日期核对"
    }
    private func detail(_ title: String,text: String) -> some View {
        VStack(alignment:.leading,spacing:5) {
            Text(title).font(.system(size:9,weight:.medium)).foregroundStyle(Palette.muted)
            Text(text).font(.system(size:11)).lineSpacing(4).foregroundStyle(Palette.ink).textSelection(.enabled).fixedSize(horizontal:false,vertical:true)
        }
    }
}
