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


# --------------------------------------------------------------------------- projet PrusaSlicer (0.6.0)

CUBE_TRIS = [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6), (0, 4, 5), (0, 5, 1), (1, 5, 6), (1, 6, 2),
             (2, 6, 7), (2, 7, 3), (3, 7, 4), (3, 4, 0)]


def cube(x, y, z, s=10.0):
    return [(x, y, z), (x + s, y, z), (x + s, y + s, z), (x, y + s, z),
            (x, y, z + s), (x + s, y, z + s), (x + s, y + s, z + s), (x, y + s, z + s)]


def mesh_xml(cubes, attrs=None):
    """Maillage de plusieurs cubes ; attrs : {rang du triangle: ' attribut="valeur"'}."""
    verts, tris = [], []
    for c in cubes:
        base = len(verts)
        verts += c
        tris += [(a + base, b + base, d + base) for a, b, d in CUBE_TRIS]
    v = "\n".join('     <vertex x="%g" y="%g" z="%g"/>' % p for p in verts)
    t = "\n".join('     <triangle v1="%d" v2="%d" v3="%d"%s/>' % (a, b, d, (attrs or {}).get(i, "")) for i, (a, b, d) in enumerate(tris))
    return "   <mesh>\n    <vertices>\n%s\n    </vertices>\n    <triangles>\n%s\n    </triangles>\n   </mesh>\n" % (v, t)


PRUSA_CFG = """; generated by PrusaSlicer 2.7.4+win64 on 2024-06-29 at 12:00:00 UTC

; bed_shape = 0x0,250x0,250x210,0x210
; extruder_colour = "#FF0000";"";"#0000FF"
; filament_colour = #FFFFFF;#00FF00;#FFFF00
; filament_settings_id = "Prusament PLA";"Prusament PETG";"Generic PLA"
; filament_type = PLA;PETG;PLA
; nozzle_diameter = 0.4,0.4,0.4
; printer_model = MK4S
; printer_settings_id = Original Prusa MK4S MMU3 0.4 nozzle
; printer_technology = %s
; support_material = 1
; support_material_auto = 1
; support_material_extruder = 3
; support_material_interface_extruder = 0
; support_material_style = organic
; wipe_tower_x = 170
; wipe_tower_y = 140
"""

PRUSA_MODEL_CFG = """<?xml version="1.0" encoding="UTF-8"?>
<config>
 <object id="1" instances_count="1">
  <metadata type="object" key="name" value="Deux cubes"/>
  <metadata type="object" key="extruder" value="0"/>
  <metadata type="object" key="perimeters" value="3"/>
  <metadata type="object" key="fuzzy_skin" value="external"/>
  <volume firstid="0" lastid="11">
   <metadata type="volume" key="name" value="cube A"/>
   <metadata type="volume" key="volume_type" value="ModelPart"/>
   <metadata type="volume" key="extruder" value="2"/>
   <metadata type="volume" key="matrix" value="1 0 0 10 0 1 0 0 0 0 1 0 0 0 0 1"/>
   <metadata type="volume" key="source_file" value="cubes.stl"/>
   <mesh edges_fixed="0" degenerate_facets="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/>
  </volume>
  <volume firstid="12" lastid="23">
   <metadata type="volume" key="name" value="modificateur"/>
   <metadata type="volume" key="volume_type" value="ParameterModifier"/>
   <metadata type="volume" key="modifier" value="1"/>
   <metadata type="volume" key="fill_density" value="40%"/>
  </volume>
 </object>
 <object id="2" instances_count="2">
  <metadata type="object" key="name" value="Cube C"/>
  <metadata type="object" key="extruder" value="3"/>
  <volume firstid="0" lastid="11">
   <metadata type="volume" key="name" value="cube C"/>
   <metadata type="volume" key="volume_type" value="ModelPart"/>
  </volume>
 </object>
</config>
"""


def prusa_3mf(path, technology="FFF"):
    """Projet PrusaSlicer : un objet de deux volumes (piece peinte + modificateur), un objet a deux
    instances (la seconde : un alias, decale de 5 mm), codes par hauteur, plage de hauteurs."""
    paint = {0: ' slic3rpe:mmu_segmentation="8"', 1: ' slic3rpe:mmu_segmentation="0C"', 5: ' slic3rpe:custom_supports="4"'}
    main = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
            'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:slic3rpe="http://schemas.slic3r.org/3mf/2017/06">\n'
            ' <metadata name="slic3rpe:Version3mf">1</metadata>\n <metadata name="slic3rpe:MmPaintingVersion">1</metadata>\n'
            ' <metadata name="Title">Cubes Prusa</metadata>\n <metadata name="Designer">Quelqu\'un</metadata>\n'
            ' <metadata name="Application">PrusaSlicer-2.7.4</metadata>\n <resources>\n'
            '  <object id="1" type="model">\n' + mesh_xml([cube(0, 0, 0), cube(2, 2, 2, 4)], paint) + '  </object>\n'
            '  <object id="2" type="model">\n' + mesh_xml([cube(0, 0, 0, 8)], {3: ' slic3rpe:mmu_segmentation="4"'}) + '  </object>\n'
            '  <object id="3" type="model">\n   <components>\n    <component objectid="2" transform="1 0 0 0 1 0 0 0 1 5 0 0"/>\n'
            '   </components>\n  </object>\n </resources>\n <build>\n'
            '  <item objectid="1" transform="1 0 0 0 1 0 0 0 1 100 100 10" printable="1"/>\n'
            '  <item objectid="2" transform="1 0 0 0 1 0 0 0 1 150 100 10" printable="1"/>\n'
            '  <item objectid="3" transform="1 0 0 0 1 0 0 0 1 150 150 10" printable="1"/>\n </build>\n</model>\n')
    gcodes = ('<?xml version="1.0" encoding="utf-8"?>\n<custom_gcodes_per_print_z>\n'
              '<code print_z="2" type="0" extruder="1" color="#FF00FF" extra="" gcode="M600"/>\n'
              '<code print_z="4" type="1" extruder="1" color="" extra="pause" gcode="M601"/>\n'
              '<mode value="SingleExtruder"/>\n</custom_gcodes_per_print_z>\n')
    ranges = ('<?xml version="1.0" encoding="utf-8"?>\n<objects>\n <object id="1">\n  <range min_z="0" max_z="1">\n'
              '   <option opt_key="extruder">1</option>\n   <option opt_key="layer_height">0.1</option>\n'
              '   <option opt_key="perimeters">5</option>\n  </range>\n </object>\n</objects>\n')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr("3D/3dmodel.model", main)
        z.writestr("Metadata/Slic3r_PE.config", PRUSA_CFG % technology)
        z.writestr("Metadata/Slic3r_PE_model.config", PRUSA_MODEL_CFG)
        z.writestr("Metadata/Prusa_Slicer_custom_gcode_per_print_z.xml", gcodes)
        z.writestr("Metadata/Prusa_Slicer_layer_config_ranges.xml", ranges)
    return path
