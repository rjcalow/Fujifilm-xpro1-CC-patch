// Create functions at every ARM 'push {..., lr}' / 'stmdb sp!' that isn't already in a function, then re-run analysis.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.mem.*;
public class MakeFuncs extends GhidraScript {
  @Override public void run() throws Exception {
    Memory m=currentProgram.getMemory(); int made=0;
    for (MemoryBlock b: m.getBlocks()) {
      Address a=b.getStart();
      while (a.compareTo(b.getEnd())<0) {
        int w=m.getInt(a);
        if ((w & 0xffff4000)==0xe92d4000 && getFunctionContaining(a)==null) {
          disassemble(a); if (createFunction(a,null)!=null) made++;
        }
        a=a.add(4);
      }
    }
    println("created "+made+" functions");
  }
}
