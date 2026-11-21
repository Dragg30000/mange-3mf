"""Fabrique des 3MF de test a partir de l'exemple pokeballs (format Bambu Studio)."""
import io, json, os, re, zipfile, math
HERE = os.path.dirname(os.path.abspath(__file__))
COLORS7 = ["#000000FF", "#FFFFFFFF", "#E53935FF", "#1E5BD8FF", "#FFE11AFF", "#6A1B9AFF", "#FF2DD4FF"]

def _origin(index, count, w, d):
    v = math.sqrt(count); r = round(v); cols = int(r + 1) if v > r else int(r)
    row, col = index // cols, index % cols
    return col * w * 1.2, -row * d * 1.2

def bambu_multiplate(path_out, bed=256.0, part_ext=None, paint_obj8=True, plate_count=6, printer="Bambu Lab X1 Carbon",
                     plate_label="Plaque"):
    z = zipfile.ZipFile(os.path.join(HERE, "samples", "sample_pokeballs.3mf"))
    files = {n: z.read(n) for n in z.namelist()}
    cfg = json.loads(files["Metadata/project_settings.config"])
    cfg["printer_model"] = printer
    cfg["printer_settings_id"] = printer + " 0.4 nozzle"
    cfg["printable_area"] = ["0x0", "%gx0" % bed, "%gx%g" % (bed, bed), "0x%g" % bed]
    cfg["filament_colour"] = list(COLORS7)
    cfg["filament_type"] = ["PLA"] * 7
    cfg["filament_settings_id"] = ["Bambu PLA Basic @BBL X1C"] * 7
    cfg["wipe_tower_x"] = [str(10 + 5 * i) for i in range(plate_count)]
    cfg["wipe_tower_y"] = [str(200 - 5 * i) for i in range(plate_count)]
    files["Metadata/project_settings.config"] = json.dumps(cfg).encode()
    main = files["3D/3dmodel.model"].decode()
    main = main.replace("BambuStudio-2.2.1", "BambuStudio-02.03.01.51")
    # une plaque par objet : on deplace chaque instance sur sa plaque (meme position locale)
    oids = ["5", "6", "7", "8", "9", "10"][:plate_count]
    def item_sub(m):
        oid = re.search(r'objectid="(\d+)"', m.group(0)).group(1)
        if oid not in oids:
            return m.group(0)
        k = oids.index(oid)
        t = re.search(r'transform="([^"]+)"', m.group(0)).group(1).split()
        ox, oy = _origin(k, plate_count, bed, bed)
        t[9] = "%g" % (float(t[9]) - 135.5 + bed / 2 + ox)
        t[10] = "%g" % (float(t[10]) - 136 + bed / 2 + oy)
        return m.group(0).replace(m.group(1), " ".join(t))
    main = re.sub(r'<item [^>]*transform="([^"]+)"[^>]*/>', item_sub, main)
    if paint_obj8:
        # objet 8 : sa premiere piece utilise une copie peinte (etat 7) du maillage 1
        main = re.sub(r'(<object id="8".*?<component p:path="/3D/Objects/bottom_white_1.model" objectid=")1(")',
                      r"\g<1>21\2", main, count=1, flags=re.S)
    files["3D/3dmodel.model"] = main.encode()
    if paint_obj8:
        sub = files["3D/Objects/bottom_white_1.model"].decode()
        mobj = re.search(r'<object id="1".*?</object>', sub, re.S).group(0)
        copy = mobj.replace('<object id="1"', '<object id="21"', 1)
        cnt = [0]
        def tri(m):
            cnt[0] += 1
            return m.group(0)[:-2] + ' paint_color="4C"/>' if cnt[0] % 3 == 0 else m.group(0)
        copy = re.sub(r'<triangle v1="\d+" v2="\d+" v3="\d+"/>', tri, copy)
        sub = sub.replace("</resources>", copy + "\n </resources>", 1)
        files["3D/Objects/bottom_white_1.model"] = sub.encode()
    ms = files["Metadata/model_settings.config"].decode()
    part_ext = part_ext or {"5": [1, 1, 1, 1], "6": [2, 2, 2, 2], "7": [3, 3, 3, 3],
                            "8": [2, 6, 2, 6], "9": [5, 1, 5, 1], "10": [4, 3, 4, 3]}
    def obj_sub(m):
        oid = m.group(1)
        body = m.group(0)
        exts = iter(part_ext.get(oid, []))
        def part_sub(pm):
            try:
                e = next(exts)
            except StopIteration:
                return pm.group(0)
            return re.sub(r'(<metadata key="extruder" value=")\d+(")', r"\g<1>%d\2" % e, pm.group(0))
        return re.sub(r"<part .*?</part>", part_sub, body, flags=re.S)
    ms = re.sub(r'<object id="(\d+)">.*?</object>', obj_sub, ms, flags=re.S)
    # plaques
    plate_tpl = re.search(r"<plate>.*?</plate>", ms, re.S).group(0)
    plates = []
    for k, oid in enumerate(oids):
        p = re.sub(r'(<metadata key="plater_id" value=")\d+(")', r"\g<1>%d\2" % (k + 1), plate_tpl)
        p = re.sub(r'(<metadata key="plater_name" value=")[^"]*(")', r"\g<1>%s %d\2" % (plate_label, k + 1), p)
        p = re.sub(r"<model_instance>.*</model_instance>",
                   '<model_instance>\n      <metadata key="object_id" value="%s"/>\n      <metadata key="instance_id" value="0"/>\n      <metadata key="identify_id" value="%d"/>\n    </model_instance>' % (oid, 100 + k), p, flags=re.S)
        plates.append(p)
    ms = ms.replace(plate_tpl, "\n  ".join(plates))
    files["Metadata/model_settings.config"] = ms.encode()
    # vignettes par plaque
    png = files.get("Metadata/plate_1_small.png", b"")
    for k in range(2, plate_count + 1):
        files["Metadata/plate_%d_small.png" % k] = png
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zo:
        for n, d in files.items():
            zo.writestr(n, d)
    open(path_out, "wb").write(buf.getvalue())
    return path_out

if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "synthetic_x1c_7colors.3mf")
    print(bambu_multiplate(out))
