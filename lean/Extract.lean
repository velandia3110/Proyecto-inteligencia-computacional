/-
Corpus de premisas del recuperador (design-document §4), sacado del MISMO commit de
Mathlib que usa el verificador. Una linea JSON por teorema de Mathlib:

  {"name", "type", "doc", "module", "premises"}

`premises` son los teoremas de Mathlib que aparecen en el termino de prueba. Es la
verdad de referencia de la curva recall@k (semana 6). Es mas ruidosa que la anotacion
de LeanDojo (incluye lo que las tacticas meten por dentro), pero tiene la ventaja de
salir del mismo commit que el corpus, sin desfase de nombres.

  cd /app/mathproj && lake env lean --run /work/lean/Extract.lean /work/data/mathlib_premises.jsonl [limite]
-/
import Lean
open Lean Meta

def isMathlib (env : Environment) (n : Name) : Bool :=
  match env.getModuleIdxFor? n with
  | some idx => (`Mathlib).isPrefixOf (env.header.moduleNames[idx.toNat]!)
  | none => false

def moduleOf (env : Environment) (n : Name) : String :=
  match env.getModuleIdxFor? n with
  | some idx => (env.header.moduleNames[idx.toNat]!).toString
  | none => ""

def isTheorem (env : Environment) (n : Name) : Bool :=
  match env.find? n with
  | some (.thmInfo _) => true
  | _ => false

def dump (out : IO.FS.Handle) (limit : Nat) : MetaM Nat := do
  let env ← getEnv
  let mut count := 0
  for (n, ci) in env.constants.map₁.toList do
    if count ≥ limit then break
    let .thmInfo t := ci | continue
    if n.isInternal || !isMathlib env n then continue
    let ty ← try pure (toString (← ppExpr t.type)) catch _ => pure ""
    if ty.isEmpty then continue
    let doc := (← findDocString? env n).getD ""
    let used := t.value.getUsedConstants.filter fun c =>
      c != n && isTheorem env c && isMathlib env c && !c.isInternal
    let prem := used.toList.eraseDups.map (fun c => toJson c.toString)
    let j := Json.mkObj [
      ("name", toJson n.toString), ("type", toJson ty), ("doc", toJson doc),
      ("module", toJson (moduleOf env n)), ("premises", Json.arr prem.toArray)]
    out.putStrLn j.compress
    count := count + 1
  return count

unsafe def main (args : List String) : IO UInt32 := do
  let path := args.headD "mathlib_premises.jsonl"
  let limit := (args.get? 1 >>= String.toNat?).getD 10000000
  initSearchPath (← findSysroot)
  enableInitializersExecution
  let env ← importModules #[{ module := `Mathlib }] {} (trustLevel := 1024)
  let out ← IO.FS.Handle.mk path .write
  let ctx : Core.Context := { fileName := "<extract>", fileMap := default, maxHeartbeats := 0 }
  let (n, _) ← (dump out limit).run'.toIO ctx { env }
  IO.println s!"{n} teoremas escritos en {path}"
  return 0
