// Decompile every function and write C to the file given as the first script argument.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import java.io.*;
public class DumpC extends GhidraScript {
  @Override public void run() throws Exception {
    String out=getScriptArgs()[0];
    DecompInterface di=new DecompInterface(); di.openProgram(currentProgram);
    try (PrintWriter pw=new PrintWriter(new BufferedWriter(new FileWriter(out)))) {
      int n=0;
      for (Function f: currentProgram.getFunctionManager().getFunctions(true)) {
        if (monitor.isCancelled()) break;
        DecompileResults r=di.decompileFunction(f,30,monitor);
        pw.println("//@@FUNC "+f.getEntryPoint()+" "+f.getName());
        if (r!=null && r.decompileCompleted()) pw.println(r.getDecompiledFunction().getC());
        else pw.println("// decompile failed");
        if (++n%500==0) println("decompiled "+n);
      }
    }
    di.dispose();
  }
}
