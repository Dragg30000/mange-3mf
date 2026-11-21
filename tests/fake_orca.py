"""Faux module « orca » pour tester le plugin hors d'OrcaSlicer."""
import io, json, sys, types, zipfile, threading

class FakeWindow:
    """Recoit les messages envoyes a la page (fenetre ou onglet) et permet de les attendre."""
    def __init__(self, **k):
        self.k = k; self.posts = []; self.open_ = True; self.cv = threading.Condition()
    def post(self, d):
        d = json.loads(json.dumps(d))
        with self.cv:
            self.posts.append(d); self.cv.notify_all()
    def is_open(self): return self.open_
    def close(self):
        self.open_ = False; cb = self.k.get("on_close"); cb and cb()
    def send(self, m): self.k["on_message"](m)
    def wait(self, cmd, n=1, timeout=60):
        import time
        end = time.time() + timeout
        with self.cv:
            while True:
                got = [p for p in self.posts if p.get("command") == cmd]
                if len(got) >= n: return got[n - 1]
                errs = [p for p in self.posts if p.get("command") == "error"]
                if errs: raise AssertionError("erreur : %s" % errs[-1]["text"])
                left = end - time.time()
                if left <= 0: raise AssertionError("pas de message %s (recus %s)" % (cmd, [p["command"] for p in self.posts]))
                self.cv.wait(left)

def template_3mf_bytes(cfg):
    """Projet enregistre comme le fait OrcaSlicer 2.5.1 : application « BambuStudio-02.08.01.55 » et
    etiquette « OrcaSlicer »."""
    main = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
            ' <metadata name="Application">BambuStudio-02.08.01.55</metadata>\n <metadata name="OrcaSlicer">2.5.1</metadata>\n'
            ' <resources>\n </resources>\n <build/>\n</model>\n')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("3D/3dmodel.model", main)
        z.writestr("Metadata/project_settings.config", json.dumps(cfg))
    return buf.getvalue()

def install(storage, template_cfg, current=None):
    orca = types.ModuleType("orca")
    state = {"windows": [], "notes": [], "perms": [], "caps": [], "exports": 0}
    cur = dict(current or template_cfg)
    def ser(v):
        if isinstance(v, list):
            if v and all(isinstance(x, str) and (x.startswith("#") or not x.replace(".", "").replace("x", "").isdigit()) for x in v) and v and v[0].startswith("#"):
                return ";".join('"%s"' % x for x in v)
            if any(x == "" or "," in x for x in v):     # comme Orca : chaines entre guillemets
                return ";".join('"%s"' % x for x in v)
            return ",".join(v)
        return str(v)
    class Preset:
        def __init__(s, name, cfg): s.name = name; s._c = cfg
        def config_value(s, k): v = s._c.get(k); return None if v is None else ser(v)
    class Bundle:
        def current_printer_preset(s): return Preset(cur.get("printer_settings_id"), cur)
        def current_process_preset(s): return Preset(cur.get("print_settings_id"), cur)
        def current_filament_preset_names(s): return list(cur.get("filament_settings_id", []))
        def full_config_value(s, k):
            v = cur.get(k)
            if v is None: return None
            if k == "filament_settings_id": return ";".join('"%s"' % x for x in v)
            return ser(v)
    class Plater:
        def export_3mf_copy(s, path):
            state["exports"] += 1
            open(path, "wb").write(template_3mf_bytes(cur))
    ui = types.SimpleNamespace()
    def create_window(**k):
        w = FakeWindow(**k); state["windows"].append(w); return w
    ui.create_window = create_window
    ui.NotificationLevel = types.SimpleNamespace(ImportantNotificationLevel="Important", WarningNotificationLevel="Warning",
                                                 RegularNotificationLevel="Regular")
    ui.push_notification = lambda lvl, txt, hyper="", cb=None: state["notes"].append((lvl, txt, hyper, cb))
    orca.host = types.SimpleNamespace(ui=ui, preset_bundle=lambda: Bundle(), plater=lambda: Plater(),
                                      plugin=types.SimpleNamespace(storage=lambda: storage))
    class Base: pass
    class ScriptBase: pass
    page = FakeWindow()
    state["page"] = page
    class PagesBase:
        """Comme orca.pages.PagesPluginCapabilityBase : post_message vers la page de l'onglet."""
        def post_message(self, data): page.post(data)
    orca.base = Base
    orca.script = types.SimpleNamespace(ScriptPluginCapabilityBase=ScriptBase)
    orca.pages = types.SimpleNamespace(PagesPluginCapabilityBase=PagesBase)
    orca.plugin = lambda cls: (state.__setitem__("plugin", cls), cls)[1]
    orca.register_capability = lambda c: state["caps"].append(c)
    orca.request_permissions = lambda **k: state["perms"].append(k)
    class ER:
        def __init__(s, kind, msg=""): s.kind = kind; s.msg = msg
        @staticmethod
        def success(m=""): return ER("success", m)
        @staticmethod
        def skipped(m=""): return ER("skipped", m)
    orca.ExecutionResult = ER
    orca.LifecycleEvent = types.SimpleNamespace(ProjectOpened="ProjectOpened", NewProject="NewProject")
    sys.modules["orca"] = orca
    return orca, state, cur
