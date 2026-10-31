import SwiftUI

struct ShareCheck:Codable {
    var state:String
    var detector:String
    var sourceCount:Int
    var redactions:Int
    var counts:[String:Int]
    var message:String
    var scope:String
    init(_ o:[String:Any]) {
        state=o["state"] as? String ?? "failed";detector=o["detector"] as? String ?? "本地识别"
        sourceCount=o["source_count"] as? Int ?? 0;redactions=o["redactions"] as? Int ?? 0
        counts=o["counts"] as? [String:Int] ?? [:];message=o["message"] as? String ?? "请核对预览";scope=o["scope"] as? String ?? "文字副本"
    }
}
struct ShareDeliveryView:View {
    let check:ShareCheck
    var body:some View {
        VStack(alignment:.leading,spacing:11) {
            HStack { Label("可分享副本已准备",systemImage:"checkmark.shield").font(.system(size:13,weight:.semibold));Spacer();Text("原件未改动").font(.system(size:10)) }
            HStack(spacing:17) { Text("完整检查 \(check.sourceCount) 份资料");Text(check.detector);Text("处理 \(check.redactions) 处") }.font(.system(size:10))
            if !check.counts.isEmpty { Text(check.counts.keys.sorted().map { "\($0) \(check.counts[$0] ?? 0)" }.joined(separator:" · ")).font(.system(size:10)).lineSpacing(4) }
            Text("\(check.message) 下方预览与导出文件使用同一份脱敏正文。").font(.system(size:11)).lineSpacing(4)
            Text(check.scope).font(.system(size:9)).foregroundStyle(Palette.muted)
        }.foregroundStyle(Palette.accent).padding(16).background(Palette.pale.opacity(0.6),in:RoundedRectangle(cornerRadius:12))
    }
}
