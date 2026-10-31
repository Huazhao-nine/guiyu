import AppKit
let target = CommandLine.arguments[1]
let image = NSImage(size:NSSize(width:1024,height:1024))
image.lockFocus()
NSColor(calibratedRed:0.19,green:0.36,blue:0.30,alpha:1).setFill()
NSBezierPath(roundedRect:NSRect(x:42,y:42,width:940,height:940),xRadius:220,yRadius:220).fill()
NSColor(calibratedRed:0.92,green:0.96,blue:0.86,alpha:1).setFill()
let mountain = NSBezierPath()
mountain.move(to:NSPoint(x:205,y:385)); mountain.line(to:NSPoint(x:432,y:725)); mountain.line(to:NSPoint(x:566,y:524)); mountain.line(to:NSPoint(x:669,y:654)); mountain.line(to:NSPoint(x:835,y:385)); mountain.close(); mountain.fill()
NSColor.white.withAlphaComponent(0.6).setFill()
NSBezierPath(roundedRect:NSRect(x:330,y:292,width:364,height:13),xRadius:6,yRadius:6).fill()
image.unlockFocus()
let rep = NSBitmapImageRep(data:image.tiffRepresentation!)!
try rep.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:target))
