"""Send a Python file into the running Unreal Editor via Remote Execution and print its output.
Usage: python tools/ue_run.py script_to_run_in_unreal.py
Bypasses Terrain Studio's runtime_sync (no files rewritten in the project)."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Unreal-Moon-Terrain-Generation" / "Terrain_Studio" / "unreal_link"))
import remote_execution as re_

code = open(sys.argv[1], encoding="utf-8").read()
s = re_.RemoteExecution()
s.start()
try:
    t0 = time.time()
    while not s.remote_nodes and time.time() - t0 < 6:
        time.sleep(0.1)
    if not s.remote_nodes:
        sys.exit("no editor found")
    s.open_command_connection(s.remote_nodes[0]["node_id"])
    r = s.run_command(code, unattended=True, exec_mode=re_.MODE_EXEC_FILE)
    for e in r.get("output", []):
        print(str(e.get("output", "")).rstrip())
    if not r.get("success"):
        print("FAILED:", r.get("result"))
finally:
    s.stop()
