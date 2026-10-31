import Foundation
import SwiftUI

extension Store {
    var isSubmissionDemo:Bool { activeWorkspace?.name=="归屿演示工作区" }
    var isNovelOfficeDemo:Bool { activeWorkspace?.name=="办公资料示例" }
    var isWorkbookDemo:Bool { activeWorkspace?.name=="通用工作簿示例" || isNovelOfficeDemo || isSubmissionDemo }
    func useSubmissionDemo() {
        guard !contextLocked,let resources=Bundle.main.resourceURL else { return }
        if let existing=workspaces.first(where:{ $0.name=="归屿演示工作区" && FileManager.default.fileExists(atPath:URL(fileURLWithPath:$0.path).appendingPathComponent(".guiyu-v27-example").path) }) {
            switchWorkspace(existing.id);intelligentExecution=true;kind = .auto;page = .workspace
            return
        }
        let id=UUID().uuidString
        let parent=baseDataDir.deletingLastPathComponent().appendingPathComponent("GuiyuExamples/"+id,isDirectory:true)
        let folder=parent.appendingPathComponent("归屿演示工作区",isDirectory:true)
        do {
            try FileManager.default.createDirectory(at:parent,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
            try FileManager.default.copyItem(at:resources.appendingPathComponent("submission-showcase"),to:folder)
            try Data("27".utf8).write(to:folder.appendingPathComponent(".guiyu-v27-example"),options:.atomic)
            workspaces.append(LocalWorkspace(id:id,name:"归屿演示工作区",path:folder.path));switchWorkspace(id)
            intelligentExecution=true;kind = .auto;page = .workspace
            notice="4 份虚构资料已就位。选择目标，按回车开始；完成后可以继续追问。"
        } catch { errorMessage="演示资料暂时无法建立，请检查本机存储后重试。" }
    }
    func useNovelOfficeDemo() {
        guard !contextLocked,let resources=Bundle.main.resourceURL else { return }
        if let existing=workspaces.first(where:{ $0.name=="办公资料示例" && FileManager.default.fileExists(atPath:URL(fileURLWithPath:$0.path).appendingPathComponent(".guiyu-v26-example").path) }) {
            switchWorkspace(existing.id);intelligentExecution=true;kind = .auto;page = .workspace
            return
        }
        let id=UUID().uuidString
        let parent=baseDataDir.deletingLastPathComponent().appendingPathComponent("GuiyuExamples/"+id,isDirectory:true)
        let folder=parent.appendingPathComponent("办公资料示例",isDirectory:true)
        do {
            try FileManager.default.createDirectory(at:parent,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
            try FileManager.default.copyItem(at:resources.appendingPathComponent("novel-office-showcase"),to:folder)
            try Data("26".utf8).write(to:folder.appendingPathComponent(".guiyu-v26-example"),options:.atomic)
            workspaces.append(LocalWorkspace(id:id,name:"办公资料示例",path:folder.path));switchWorkspace(id)
            intelligentExecution=true;kind = .auto;page = .workspace
            notice="台账、报价、服务记录和活动资料已就位。直接说出目标，完成后接着追问。"
        } catch { errorMessage="办公示例暂时无法建立，请检查本机存储后重试。" }
    }
    func useWorkbookDemo() {
        guard !contextLocked,let resources=Bundle.main.resourceURL else { return }
        let id=UUID().uuidString
        let parent=baseDataDir.deletingLastPathComponent().appendingPathComponent("GuiyuExamples/"+id,isDirectory:true)
        let folder=parent.appendingPathComponent("通用工作簿示例",isDirectory:true)
        do {
            try FileManager.default.createDirectory(at:parent,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
            try FileManager.default.copyItem(at:resources.appendingPathComponent("workbook-showcase"),to:folder)
            workspaces.append(LocalWorkspace(id:id,name:"通用工作簿示例",path:folder.path));switchWorkspace(id)
            intelligentExecution=true;kind = .auto;page = .workspace
            notice="4份虚构工作簿已就位。选一件工作，或直接说出自己的目标。"
        } catch { errorMessage="工作簿示例暂时无法建立，请检查本机存储后重试。" }
    }
    func fillWorkbookExample(_ goal:String) {
        guard !contextLocked else { return }
        newTask();intelligentExecution=true;kind = .auto;prompt=goal
    }
}

struct WorkbookShowcaseView:View {
    @EnvironmentObject var store:Store
    private var tasks:[(String,String,String)] { store.isSubmissionDemo ? [
        ("工作簿：汇总并交付 Word","tablecells","处理支持日志.xlsx，按线上、线下的顺序合并，先按TicketID保留首次记录。ClosedDate从2028年4月1日（含）到7月1日（不含），Category为保修，或者Category为回访且Confirmed为true；每条Cost至少50元。按Owner汇总累计时长、支出和记录数，累计时长用小时、支出用万元显示，按支出降序，同金额按Owner升序。只保留Owner、累计时长、支出、记录数四列，另存一份Word，标题“支持工作汇总”。"),
        ("活动：核算最新费用与日期","calendar","结合共享工位安排和最新通知，按最新版本整理一份Word，说明活动费用、预算余额和最晚确认日期。可退押金单独说明，不计入活动费用，保留未付款状态，列出费用明细和出处。"),
        ("分享：自动识别与脱敏","checkmark.shield","把客户跟进纪要.md整理成可分享版本，保留全部正文、预算、办公日期和尚未付款的条件，给我Word副本。")
    ] : store.isNovelOfficeDemo ? [
        ("库存：明细与汇总","shippingbox","从公开台账中找出2027年8月入库、申领使用备注不含撤销、剩余数量不少于0且小于6、入库单价非空的记录。计算现存金额=剩余数量乘入库单价，按金额从高到低，输出耗材名称、剩余数量、现存金额，附总额和条数，并给一份Word。"),
        ("报价：复杂条件与重算","line.3.horizontal.decrease.circle","整理公开报价：单价非空，且数量至少3或品牌为海岚。重新计算合价，按合价从高到低，只保留设备名称、数量、单价、合价，附总额和条数，给一份Word。"),
        ("服务：去重与单位换算","chart.bar.xaxis","合并服务记录的东西两张表，按VisitID先去重保留首次，再筛2027年12月、满足（已结案或（待复核且Remote为true））、原始Paid不少于100元的记录。按Team汇总工时、费用和条数，按费用降序；工时用小时、费用用元显示，并给Word。"),
        ("活动：读取最新变更","calendar","结合读书会方案和变更记录，按最新内容核算费用、预算余额和确认日期，保留尚未付款的条件，写一份简洁Word供核对。")
    ] : [
        ("采购：组合条件与余额","line.3.horizontal.decrease.circle","在采购协作的采购明细中，部门为研发或行政，并且付款状态为待付款或部分付款，计算未付金额=应付减已付。只要未付金额不少于600元的订单，按未付金额从高到低排列，只保留订单编号、部门、供应商、未付金额。"),
        ("销售：理解两层表头","chart.bar.xaxis","经营报表的销售页有两层表头。按区域汇总10月实际销售额，不要把11月数据或合计行算进去，按10月实际合计从高到低排列，只要区域和10月实际合计。"),
        ("库存：缺口与补货成本","shippingbox","从库存台账找出库存低于安全库存的物料。计算缺口=安全库存减现有库存，补货成本=缺口乘单价。按补货成本由高到低排列，只要物料编号、缺口、补货成本。"),
        ("报名：合并、去重与分组","person.2","合并活动报名的活动甲和活动乙，排除已取消和邮箱为空的记录，再按邮箱去重、保留首次记录。按机构统计独立联系人数，人数从多到少，同人数按机构升序。")]
    }
    var body:some View {
        VStack(alignment:.leading,spacing:20) {
            Label(store.isSubmissionDemo ? "归屿演示工作区" : (store.isNovelOfficeDemo ? "办公资料示例" : "通用工作簿示例"),systemImage:"tablecells").font(.system(size:11,weight:.medium)).foregroundStyle(Palette.accent)
            Text(store.isSubmissionDemo ? "说出目标。\n成果留在你的电脑。" : "不必先弄懂表格。\n说出你要的结果。").font(.custom("Songti SC",size:30)).foregroundStyle(Palette.ink)
            Text(store.isSubmissionDemo ? "选择一个目标，按回车开始。归屿会查找资料、组合工具并检查结果。表格任务完成后，可以追问“只要第一名，其他口径不变”。" : "先检查工作表、表头与数据，再安排筛选、计算和统计。完成后继续说“其他条件不变，把门槛改成300元”。")
                .font(.system(size:12)).foregroundStyle(Palette.muted).lineSpacing(6)
            LazyVGrid(columns:[GridItem(.flexible()),GridItem(.flexible())],spacing:12) {
                ForEach(tasks.indices,id:\.self) { i in
                    Button { store.fillWorkbookExample(tasks[i].2) } label: {
                        VStack(alignment:.leading,spacing:14) {
                            Image(systemName:tasks[i].1).font(.system(size:20)).foregroundStyle(Palette.accent)
                            Text(tasks[i].0).font(.system(size:13,weight:.medium)).foregroundStyle(Palette.ink)
                            Text(tasks[i].2).font(.system(size:10)).foregroundStyle(Palette.muted).lineLimit(3).lineSpacing(4)
                        }.frame(maxWidth:.infinity,minHeight:135,alignment:.topLeading).padding(18)
                            .background(Color.white,in:RoundedRectangle(cornerRadius:14))
                            .overlay(RoundedRectangle(cornerRadius:14).stroke(Palette.line))
                    }.buttonStyle(.plain).disabled(store.contextLocked)
                }
            }
            Label("全程本机 · 原文件保留 · 结果可预览、可导出",systemImage:"lock").font(.system(size:10)).foregroundStyle(Palette.muted)
        }.padding(.vertical,8)
    }
}
