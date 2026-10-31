import Foundation

enum DevicePolicy {
    static let dailyModelID = PrimaryModel.id
    static let baselineBytes: UInt64 = 32 * 1024 * 1024 * 1024
    static var deviceMemoryGB: Int { Int(ProcessInfo.processInfo.physicalMemory / 1024 / 1024 / 1024) }
    static func allows(_ model: LocalModelOption, memoryBytes: UInt64 = ProcessInfo.processInfo.physicalMemory) -> Bool {
        memoryBytes >= baselineBytes || (model.id != PrimaryModel.id && model.bytes <= 7 * 1024 * 1024 * 1024)
    }
}
