import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct PrivacyRedactionView: View {
    @EnvironmentObject var store:Store
    @StateObject private var worker=PrivacyScanWorker()
    @AppStorage("guiyu.privacy.detector") private var detector="rules"
    @AppStorage("guiyu.privacy.names") private var hideNames=true
    @AppStorage("guiyu.privacy.addresses") private var hideAddresses=true
    @AppStorage("guiyu.privacy.dates") private var hideDates=false
    @AppStorage("guiyu.privacy.accounts") private var hideAccounts=true
    @AppStorage("guiyu.privacy.network") private var hideNetwork=false
    @ViewState private var text=""
    @ViewState private var words=""
    @ViewState private var allow=""
    @ViewState private var prefixes=""
    @AppStorage("guiyu.privacy.secrets") private var hideSecrets=true
    @AppStorage("guiyu.privacy.contacts") private var hidePersonal=true
    @ViewState private var expanded=false
    @ViewState private var output=""
    @ViewState private var counts=""
    @ViewState private var busy=false
    @ViewState private var message=""
    @ViewState private var epoch=UUID()
    private func entries(_ s:String)->[String] { s.components(separatedBy:CharacterSet(charactersIn:",，\n")).map{$0.trimmingCharacters(in:.whitespacesAndNewlines)}.filter{!$0.isEmpty} }
    private func invalidate() { worker.cancel();epoch=UUID();output="";counts="";message="";busy=false }
    var body: some View {
        VStack(alignment:.leading,spacing:17) {
            HStack { Label("分享前，先留住隐私",systemImage:"eye.slash").font(.system(size:15,weight:.semibold));Spacer();Text("本地识别 · 按需运行").font(.system(size:10)).foregroundStyle(Palette.accent) }
            Text("粘贴要分享的文字，或带入当前结果。先预览遮盖内容，再复制或保存脱敏副本。原文和检查内容不写入工作记录。对话中说“整理成可分享版本”即可自动处理；分享任务默认使用 AstrLink，选择 OpenAI 后会沿用。分类开关会在本机记住。")
                .font(.system(size:11)).foregroundStyle(Palette.muted).lineSpacing(5)
            componentPicker
            HStack(spacing:18) { Toggle("姓名",isOn:$hideNames);Toggle("地址",isOn:$hideAddresses);Toggle("遮盖密钥与密码",isOn:$hideSecrets);Toggle("联系方式",isOn:$hidePersonal) }.font(.system(size:11)).toggleStyle(.switch).controlSize(.small)
            DisclosureGroup("自定义词、密钥前缀与保留名单",isExpanded:$expanded) {
                VStack(spacing:10) {
                    HStack { Toggle("账号与证件",isOn:$hideAccounts);Toggle("私人日期",isOn:$hideDates);Toggle("IP 与网址",isOn:$hideNetwork) }.toggleStyle(.switch).controlSize(.small)
                    Text("办公金额默认保护；私人日期关闭时保留普通日期。明确标注的密码仍会遮盖。模型可能漏检，分享前请核对。").font(.system(size:10)).foregroundStyle(Palette.muted).frame(maxWidth:.infinity,alignment:.leading)
                    TextField("额外遮盖的姓名、地址或项目代号，用逗号分隔",text:$words)
                    TextField("自建密钥前缀，例如 oc_sk_，用逗号分隔",text:$prefixes)
                    TextField("保留原样的完整值，用逗号分隔（忽略大小写）",text:$allow)
                    Text("保留名单仅匹配整个识别值；自定义词忽略大小写。名单仅用于本次预览，离开后清除。")
                        .font(.system(size:10)).foregroundStyle(Palette.muted).frame(maxWidth:.infinity,alignment:.leading)
                }.textFieldStyle(.roundedBorder).padding(.top,10)
            }.font(.system(size:11)).foregroundStyle(Palette.accent)
            TextEditor(text:$text).font(.system(size:12)).scrollContentBackground(.hidden).padding(10)
                .frame(height:130).background(Palette.background,in:RoundedRectangle(cornerRadius:9))
                .overlay(RoundedRectangle(cornerRadius:9).stroke(Palette.line))
                .accessibilityLabel("待脱敏文字")
            HStack(spacing:16) {
                Button("带入当前结果") { invalidate();text=store.current?.displayText ?? "" }.disabled(store.current == nil)
                Button("试用虚构文本") { invalidate();text="请联系林晓，邮箱 linxiao@example.com，手机号 13812345678。地址北京市海淀区中关村大街27号。api_key=sk-proj-fictionalSecret123456789。预算1280元，截止日期2026-10-31。" }
                Spacer()
                Text("\(text.count)/24,000").font(.system(size:9)).foregroundStyle(Palette.muted)
                Button(busy ? "正在本机检查…" : "预览脱敏") { scan() }.buttonStyle(.borderedProminent).tint(Palette.accent).disabled(busy || text.isEmpty || text.count>24000 || !componentReady)
                if busy { Button("取消") { invalidate() } }
            }.font(.system(size:11)).buttonStyle(.plain)
            if !output.isEmpty {
                HStack { Label(counts,systemImage:"checkmark.shield");Spacer();Text("不保存原文或还原映射").foregroundStyle(Palette.muted) }.font(.system(size:10)).foregroundStyle(Palette.accent)
                ScrollView { Text(output).font(.system(size:12)).textSelection(.enabled).lineSpacing(5).frame(maxWidth:.infinity,alignment:.leading).padding(14) }
                    .frame(height:145).background(Palette.pale.opacity(0.5),in:RoundedRectangle(cornerRadius:9))
                HStack(spacing:17) {
                    Button("复制脱敏文本") { NSPasteboard.general.clearContents();NSPasteboard.general.setString(output,forType:.string);message="已复制脱敏文本，请在分享前检查。" }
                    Button("保存脱敏副本") { saveCopy() }
                    Spacer();Button("清除本次内容") { invalidate();text="";words="";allow="";prefixes="" }
                }.font(.system(size:11)).buttonStyle(.plain).foregroundStyle(Palette.accent)
            }
            Text(message.isEmpty ? "识别可能漏检或误判。规则模式下姓名和地址请添加自定义词。脱敏副本不会自动还原敏感值。" : message).font(.system(size:10)).foregroundStyle(Palette.muted).lineSpacing(4)
        }.padding(24).card()
        .onChange(of:text) { invalidate() }.onChange(of:words) { invalidate() }.onChange(of:allow) { invalidate() }
        .onChange(of:prefixes) { invalidate() }.onChange(of:hideSecrets) { invalidate() }.onChange(of:hidePersonal) { invalidate() }
        .onChange(of:detector) { invalidate() }.onChange(of:hideNames) { invalidate() }.onChange(of:hideAddresses) { invalidate() }
        .onChange(of:hideDates) { invalidate() }.onChange(of:hideAccounts) { invalidate() }.onChange(of:hideNetwork) { invalidate() }
        .onDisappear { invalidate();text="";words="";allow="";prefixes="" }
    }
    private func scan() {
        let generation=UUID();epoch=generation;busy=true;output="";message=""
        let request:[String:Any] = ["text":text,"detector":detector,"policy":["words":entries(words),"allow":entries(allow),"prefixes":entries(prefixes),"secrets":hideSecrets,"personal":hidePersonal,"categories":["person":hideNames,"address":hideAddresses,"date":hideDates,"account":hideAccounts,"identity":hideAccounts,"bank":hideAccounts,"ip":hideNetwork,"url":hideNetwork]]]
        guard store.hostSandboxed,let data=try? JSONSerialization.data(withJSONObject:request) else { busy=false;message="本地隔离尚未确认，请重新打开归屿。";return }
        let script=Bundle.main.resourceURL!.appendingPathComponent("privacy_filter.py")
        let python=FileManager.default.urls(for:.applicationSupportDirectory,in:.userDomainMask)[0].appendingPathComponent("GuiyuRuntime/python/bin/python")
        worker.start(data:data,python:python,script:script) { result in
            guard epoch==generation else { return };busy=false
            guard let result,let redacted=result["text"] as? String else { message="本次检查未完成，未生成可分享副本。组件可能未就绪或内容过长，请重试或明确切换规则模式。";return }
            output=redacted;counts="发现并遮盖 \(result["count"] as? Int ?? 0) 处 · \(result["detector"] as? String ?? "本地识别")"
        }
    }
    private var selectedComponent:CatalogModel? { store.modelCatalog.first{$0.isPrivacy && $0.id==detector} }
    private var componentReady:Bool { detector=="rules" || selectedComponent.map { store.privacyComponentReady($0) } == true }
    private var componentPicker:some View {
        VStack(alignment:.leading,spacing:9) {
            HStack(spacing:14) {
                Picker("识别方式",selection:$detector) {
                    Text("规则 · 无需下载").tag("rules")
                    ForEach(store.modelCatalog.filter{$0.isPrivacy}) { item in Text(item.name).tag(item.id) }
                }.pickerStyle(.menu).frame(maxWidth:340)
                Spacer()
                if let item=selectedComponent {
                    if componentReady { Label("已在本机",systemImage:"checkmark.circle.fill").font(.system(size:10)).foregroundStyle(Palette.accent) }
                    else if store.downloadStatuses[item.id]?.active == true {
                        Button("暂停下载") { store.requestModelDownload(item,pause:true) }.disabled(store.downloadStatuses[item.id]?.phase=="pausing")
                    } else {
                        Button(store.downloadStatuses[item.id]?.phase=="paused" ? "继续下载" : "一键下载") { store.requestModelDownload(item) }.buttonStyle(.borderedProminent).tint(Palette.accent).disabled(store.anyDownloadActive)
                    }
                }
            }.font(.system(size:11))
            if let item=selectedComponent {
                Text("\(item.badge) · 下载 \(ByteCountFormatter.string(fromByteCount:item.bytes,countStyle:.file)) · CPU 按需加载，检查后释放。与对话模型独立。").font(.system(size:10)).foregroundStyle(Palette.muted)
                if !componentReady,let status=store.downloadStatuses[item.id] {
                    ProgressView(value:status.progress).tint(Palette.accent)
                    Text(status.detail).font(.system(size:10)).foregroundStyle(status.phase=="failed" ? Palette.warm : Palette.muted)
                }
            } else { Text("格式规则立即可用；选择本地模型可自动识别姓名、地址。下载仅获取公开组件，不接收检查文字。").font(.system(size:10)).foregroundStyle(Palette.muted) }
        }.padding(12).background(Palette.pale.opacity(0.5),in:RoundedRectangle(cornerRadius:10))
    }
    private func saveCopy() {
        let snapshot=output;let panel=NSSavePanel();panel.nameFieldStringValue="脱敏副本.txt";panel.allowedContentTypes=[.plainText];panel.prompt="保存副本"
        panel.begin { response in
            guard response == .OK,let url=panel.url else { return }
            do { try Data(snapshot.utf8).write(to:url,options:.withoutOverwriting);message="已保存脱敏副本，原文件保持不变。" }
            catch { message="未保存。如果目标已有同名文件，请换一个名称。" }
        }
    }
}
