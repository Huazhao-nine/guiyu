// QA-only file conversion using the exact native Codable schema. No Store,
// model, UI automation, original-file access or normal application state.
import Foundation

@main
struct NativeRecordConverter {
    static func main() throws {
        guard CommandLine.arguments.count==3 else { throw NSError(domain:"QA",code:1) }
        let input=URL(fileURLWithPath:CommandLine.arguments[1])
        let output=URL(fileURLWithPath:CommandLine.arguments[2])
        let objects=try JSONSerialization.jsonObject(with:Data(contentsOf:input)) as! [[String:Any]]
        let records=objects.map { TaskRecord($0) }.sorted { $0.created > $1.created }
        let data=try JSONEncoder().encode(records)
        let replay=try JSONDecoder().decode([TaskRecord].self,from:data)
        precondition(replay.count==records.count)
        precondition(zip(records,replay).allSatisfy { $0.id==$1.id && $0.toolCalls?.count==$1.toolCalls?.count })
        try data.write(to:output,options:.atomic)
        print("Converted \(records.count) fictional records with native Codable roundtrip.")
    }
}
