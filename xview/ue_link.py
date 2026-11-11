"""Host side: run Python inside the open Unreal Editor and get replies back.

Uses Epic's remote_execution.py (the copy in Terrain Studio's repo). Doesn't go
through Terrain Studio's runtime_sync, so nothing gets written into the MARE project.
One editor, one command at a time.
"""
import json
import time
from pathlib import Path

MARE = Path(__file__).resolve().parent.parent
TS_LINK = MARE / "Unreal-Moon-Terrain-Generation" / "Terrain_Studio" / "unreal_link"
TS_COMMANDS = MARE / "Unreal-Moon-Terrain-Generation" / "Terrain_Studio" / "unreal_commands"
UNREAL_SIDE = Path(__file__).resolve().parent / "unreal_side"
REPLY = "XVIEW_JSON "

import sys  # noqa: E402
sys.path.insert(0, str(TS_LINK))
import remote_execution  # noqa: E402


class UnrealLink:
    """with UnrealLink() as ue: ue.call("xview_rig", "ensure_rig", cfg)"""

    def __enter__(self):
        self.session = remote_execution.RemoteExecution()
        self.session.start()
        t0 = time.time()
        while not self.session.remote_nodes and time.time() - t0 < 6:
            time.sleep(0.1)
        if not self.session.remote_nodes:
            self.session.stop()
            raise RuntimeError("No Unreal Editor found (is it open, with Remote Execution enabled?)")
        self.session.open_command_connection(self.session.remote_nodes[0]["node_id"])
        return self

    def __exit__(self, *exc):
        self.session.stop()

    def run(self, code):
        """Runs code in the editor. Returns (printed lines, replies parsed from REPLY lines)."""
        result = self.session.run_command(code, unattended=True,
                                          exec_mode=remote_execution.MODE_EXEC_FILE)
        lines = [str(e.get("output", "")).rstrip() for e in result.get("output", [])]
        replies = [json.loads(l[len(REPLY):]) for l in lines if l.startswith(REPLY)]
        if not result.get("success"):
            raise RuntimeError("Unreal raised:\n" + "\n".join(lines) + "\n" + str(result.get("result")))
        return lines, replies

    def call(self, module, function, *args, **kwargs):
        """Calls module.function(*args, **kwargs) inside the editor; returns its last reply.
        The module is (re)loaded from xview/unreal_side or Terrain Studio's unreal_commands."""
        argtext = ", ".join([repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()])
        code = "\n".join([
            "import sys, importlib",
            *[f"sys.path.insert(0, {str(p)!r}) if {str(p)!r} not in sys.path else None"
              for p in (UNREAL_SIDE, TS_COMMANDS)],
            f"import {module}",
            f"importlib.reload({module})",
            f"_r = {module}.{function}({argtext})",
            f"print({REPLY!r} + __import__('json').dumps({{'return': str(_r)}})) if _r is not None else None",
        ])
        lines, replies = self.run(code)
        if replies and "error" in replies[-1]:
            raise RuntimeError(replies[-1]["error"])
        return replies[-1] if replies else None


def set_sun_studio(link, studio_azimuth_deg, elevation_deg, intensity_lux=120000.0):
    """Terrain Studio's unreal_sun.set_sun, without saving the level."""
    return link.call("unreal_sun", "set_sun", float(studio_azimuth_deg), float(elevation_deg),
                     intensity_lux=float(intensity_lux), save_level=False)
