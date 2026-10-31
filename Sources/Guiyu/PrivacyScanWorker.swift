import Foundation
import Combine

// A serial lane owns the process through exit. Cancellation invalidates queued
// work and terminates the active child before a newer model can be loaded.
final class PrivacyScanWorker:ObservableObject {
    private let queue=DispatchQueue(label:"org.guiyu.privacy",qos:.userInitiated)
    private let lock=NSLock()
    private var epoch=UUID()
    private var process:Process?
    func cancel() {
        lock.lock();epoch=UUID();let child=process;lock.unlock()
        if child?.isRunning == true { child?.terminate() }
    }
    func start(data:Data,python:URL,script:URL,completion:@escaping([String:Any]?)->Void) {
        cancel();lock.lock();let token=epoch;lock.unlock()
        queue.async { [self] in
            let child=Process(),input=Pipe(),output=Pipe()
            child.executableURL=python;child.arguments=["-I","-B",script.path]
            child.standardInput=input;child.standardOutput=output;child.standardError=FileHandle.nullDevice
            child.environment=["PATH":"/usr/bin:/bin","PYTHONDONTWRITEBYTECODE":"1","HF_HUB_OFFLINE":"1","TOKENIZERS_PARALLELISM":"false"]
            lock.lock()
            guard epoch==token else { lock.unlock();return }
            do { try child.run();process=child } catch { lock.unlock();DispatchQueue.main.async{completion(nil)};return }
            lock.unlock()
            DispatchQueue.global().asyncAfter(deadline:.now()+180) { [weak self] in
                guard let self else { return };self.lock.lock();let active=self.epoch==token && self.process===child;self.lock.unlock()
                if active && child.isRunning { child.terminate() }
            }
            var result:[String:Any]?
            do {
                try input.fileHandleForWriting.write(contentsOf:data+Data([10]));try input.fileHandleForWriting.close()
                let response=output.fileHandleForReading.readDataToEndOfFile();child.waitUntilExit()
                if child.terminationStatus==0 && response.count<=600000 { result=try JSONSerialization.jsonObject(with:response) as? [String:Any] }
            } catch { if child.isRunning { child.terminate() };child.waitUntilExit() }
            lock.lock();let valid=epoch==token;process=nil;lock.unlock()
            if valid { let captured=result;DispatchQueue.main.async { completion(captured) } }
        }
    }
    deinit { cancel() }
}
