"""VRM LOADER — Carregador universal de modelos 3D VRM 1.0, VRM 0.x e glTF 2.0 (.vrm / .glb) em NumPy puro.

Extrai hierarquia de nós, esqueletos (`skins` + `inverseBindMatrices`), mapeamento humanoide VRM,
malhas (`POSITION`, `NORMAL`, `TEXCOORD_0`, `JOINTS_0`, `WEIGHTS_0`, índices), morph targets
(inclusive accessors esparsos), expressões faciais VRM, grupos de física SpringBone e materiais/texturas.
"""

from dataclasses import dataclass, field
import io
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image

_COMP_DTYPE = {
    5120: np.int8,
    5121: np.uint8,
    5122: np.int16,
    5123: np.uint16,
    5125: np.uint32,
    5126: np.float32,
}

_TYPE_COUNT = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}


@dataclass
class VrmNode:
    index: int
    name: str
    parent: int = -1
    children: list[int] = field(default_factory=list)
    translation: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float32))
    rotation: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32))  # xyzw
    scale: np.ndarray = field(default_factory=lambda: np.ones(3, dtype=np.float32))
    mesh: int = -1
    skin: int = -1


@dataclass
class VrmMaterial:
    index: int
    name: str
    role: str  # hair | eye | tops | bottoms | shoes | skin | face | other
    base_color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    shade_color: tuple[float, float, float] = (0.82, 0.78, 0.86)
    texture_rgba: np.ndarray | None = None  # (H, W, 4) uint8
    alpha_mode: str = "OPAQUE"  # OPAQUE | MASK | BLEND
    alpha_cutoff: float = 0.5
    double_sided: bool = False


@dataclass
class VrmPrimitive:
    mesh_index: int
    skin_index: int
    material_index: int
    positions: np.ndarray      # (V, 3) float32
    normals: np.ndarray        # (V, 3) float32
    uvs: np.ndarray            # (V, 2) float32
    joints: np.ndarray         # (V, 4) float32 (índices de joint convertidos para float32)
    weights: np.ndarray        # (V, 4) float32
    indices: np.ndarray        # (I,) uint32
    morph_deltas: list[np.ndarray] = field(default_factory=list)  # lista de (V, 3) float32


@dataclass
class VrmSkin:
    joints: list[int]
    inv_bind_matrices: np.ndarray  # (J, 4, 4) float32 em forma matemática padrão (translação na col 3)


@dataclass
class VrmSpringChain:
    joints: list[int]
    stiffness: float = 1.0
    drag: float = 0.45
    gravity_power: float = 0.12


@dataclass
class VrmConstraint:
    node: int
    kind: str  # "aim" | "roll" | "rotation"
    source: int
    axis: str = "PositiveX"
    weight: float = 1.0


@dataclass
class VrmModel:
    name: str
    is_vrm1: bool
    nodes: list[VrmNode]
    roots: list[int]
    skins: list[VrmSkin]
    materials: list[VrmMaterial]
    primitives: list[VrmPrimitive]
    humanoid_bones: dict[str, int]
    expressions: dict[str, list[tuple[int, int, float]]]  # expr_name -> [(mesh_idx, morph_idx, weight)]
    springs: list[VrmSpringChain]
    constraints: list[VrmConstraint] = field(default_factory=list)
    height: float = 1.60
    min_y: float = 0.0


def _classify_material_role(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ("hair", "bang", "ahoge", "ponytail")):
        return "hair"
    if any(k in n for k in ("eyeiris", "iris", "pupil", "eye_")):
        return "eye"
    if any(k in n for k in ("eyewhite", "eyehighlight", "eyeline", "brow", "mouth", "face")):
        return "face"
    if any(k in n for k in ("top", "shirt", "jacket", "sweater", "dress", "coat", "huku", "cloth_top")):
        return "tops"
    if any(k in n for k in ("bottom", "skirt", "pants", "short", "stocking", "sock")):
        return "bottoms"
    if any(k in n for k in ("shoe", "boot", "heel", "sandal")):
        return "shoes"
    if any(k in n for k in ("skin", "body")):
        return "skin"
    return "other"


def _read_accessor(gltf: dict, bin_chunk: bytes, acc_idx: int) -> np.ndarray:
    acc = gltf["accessors"][acc_idx]
    comp_type = acc["componentType"]
    dtype = _COMP_DTYPE[comp_type]
    n_comp = _TYPE_COUNT[acc["type"]]
    count = int(acc["count"])
    itemsize = np.dtype(dtype).itemsize

    if "bufferView" in acc:
        bv = gltf["bufferViews"][acc["bufferView"]]
        base_off = int(bv.get("byteOffset", 0)) + int(acc.get("byteOffset", 0))
        stride = int(bv.get("byteStride", 0)) or (n_comp * itemsize)
        if stride == n_comp * itemsize:
            arr = np.frombuffer(bin_chunk, dtype=dtype, count=count * n_comp, offset=base_off).copy()
            arr = arr.reshape((count, n_comp)) if n_comp > 1 else arr
        else:
            raw = np.frombuffer(bin_chunk, dtype=np.uint8, count=count * stride, offset=base_off)
            raw = raw.reshape((count, stride))[:, : n_comp * itemsize]
            arr = np.frombuffer(np.ascontiguousarray(raw), dtype=dtype).copy()
            arr = arr.reshape((count, n_comp)) if n_comp > 1 else arr
    else:
        arr = np.zeros((count, n_comp) if n_comp > 1 else (count,), dtype=dtype)

    # Suporte a accessors esparsos (comum em morph targets do VRM 1.0!)
    if "sparse" in acc:
        sp = acc["sparse"]
        sp_count = int(sp["count"])
        idx_info = sp["indices"]
        idx_bv = gltf["bufferViews"][idx_info["bufferView"]]
        idx_off = int(idx_bv.get("byteOffset", 0)) + int(idx_info.get("byteOffset", 0))
        idx_dtype = _COMP_DTYPE[idx_info["componentType"]]
        sp_indices = np.frombuffer(bin_chunk, dtype=idx_dtype, count=sp_count, offset=idx_off)

        val_info = sp["values"]
        val_bv = gltf["bufferViews"][val_info["bufferView"]]
        val_off = int(val_bv.get("byteOffset", 0)) + int(val_info.get("byteOffset", 0))
        sp_vals = np.frombuffer(bin_chunk, dtype=dtype, count=sp_count * n_comp, offset=val_off)
        if n_comp > 1:
            sp_vals = sp_vals.reshape((sp_count, n_comp))
        arr[sp_indices] = sp_vals

    if acc.get("normalized") and np.issubdtype(dtype, np.integer):
        arr = arr.astype(np.float32) / float(np.iinfo(dtype).max)
    return arr


def _decode_image_rgba(gltf: dict, bin_chunk: bytes, img_idx: int) -> np.ndarray | None:
    try:
        info = gltf["images"][img_idx]
        if "bufferView" not in info:
            return None
        bv = gltf["bufferViews"][info["bufferView"]]
        off = int(bv.get("byteOffset", 0))
        length = int(bv["byteLength"])
        raw = bin_chunk[off : off + length]
        with Image.open(io.BytesIO(raw)) as im:
            rgba = im.convert("RGBA")
            # Limita a 1024px para carregamento instantâneo e baixo consumo de VRAM
            if max(rgba.width, rgba.height) > 1024:
                rgba.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            return np.asarray(rgba, dtype=np.uint8).copy()
    except Exception:
        return None


def _decompose_matrix(mat_col_major: list[float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Decompõe uma matriz 4x4 glTF (column-major) em (translation, quat_xyzw, scale)."""
    m = np.array(mat_col_major, dtype=np.float32).reshape((4, 4)).T
    t = m[:3, 3].copy()
    sx = float(np.linalg.norm(m[:3, 0])) or 1.0
    sy = float(np.linalg.norm(m[:3, 1])) or 1.0
    sz = float(np.linalg.norm(m[:3, 2])) or 1.0
    r = np.column_stack([m[:3, 0] / sx, m[:3, 1] / sy, m[:3, 2] / sz])
    tr = float(r[0, 0] + r[1, 1] + r[2, 2])
    if tr > 0.0:
        s = np.sqrt(tr + 1.0) * 2.0
        qw = 0.25 * s
        qx = (r[2, 1] - r[1, 2]) / s
        qy = (r[0, 2] - r[2, 0]) / s
        qz = (r[1, 0] - r[0, 1]) / s
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = np.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2.0
        qw = (r[2, 1] - r[1, 2]) / s
        qx = 0.25 * s
        qy = (r[0, 1] + r[1, 0]) / s
        qz = (r[0, 2] + r[2, 0]) / s
    elif r[1, 1] > r[2, 2]:
        s = np.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2.0
        qw = (r[0, 2] - r[2, 0]) / s
        qx = (r[0, 1] + r[1, 0]) / s
        qy = 0.25 * s
        qz = (r[1, 2] + r[2, 1]) / s
    else:
        s = np.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2.0
        qw = (r[1, 0] - r[0, 1]) / s
        qx = (r[0, 2] + r[2, 0]) / s
        qy = (r[1, 2] + r[2, 1]) / s
        qz = 0.25 * s
    q = np.array([qx, qy, qz, qw], dtype=np.float32)
    q /= max(float(np.linalg.norm(q)), 1e-6)
    return t, q, np.array([sx, sy, sz], dtype=np.float32)


def load_vrm(path: Path) -> VrmModel:
    """Carrega um arquivo `.vrm` (VRM 1.0 ou 0.x) ou `.glb` em um `VrmModel` pronto para animação e GPU."""
    raw = Path(path).read_bytes()
    if len(raw) < 20:
        raise ValueError(f"Arquivo GLB/VRM inválido: {path}")
    magic, _version, _total_len = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF":
        raise ValueError(f"Cabeçalho glTF ausente em {path}")

    json_len, json_type = struct.unpack_from("<II", raw, 12)
    if json_type != 0x4E4F534A:  # JSON
        raise ValueError("Primeiro chunk do GLB não é JSON")
    gltf = json.loads(raw[20 : 20 + json_len].decode("utf-8"))

    bin_off = 20 + json_len
    bin_chunk = b""
    if bin_off + 8 <= len(raw):
        bin_len, bin_type = struct.unpack_from("<II", raw, bin_off)
        if bin_type == 0x004E4942:  # BIN
            bin_chunk = raw[bin_off + 8 : bin_off + 8 + bin_len]

    # 1. Nós & hierarquia
    raw_nodes = gltf.get("nodes", [])
    nodes: list[VrmNode] = []
    for idx, n in enumerate(raw_nodes):
        if "matrix" in n:
            t, q, s = _decompose_matrix(n["matrix"])
        else:
            t = np.array(n.get("translation", [0.0, 0.0, 0.0]), dtype=np.float32)
            q = np.array(n.get("rotation", [0.0, 0.0, 0.0, 1.0]), dtype=np.float32)
            s = np.array(n.get("scale", [1.0, 1.0, 1.0]), dtype=np.float32)
        nodes.append(
            VrmNode(
                index=idx,
                name=str(n.get("name", f"node_{idx}")),
                children=list(n.get("children", [])),
                translation=t,
                rotation=q,
                scale=s,
                mesh=int(n["mesh"]) if "mesh" in n else -1,
                skin=int(n["skin"]) if "skin" in n else -1,
            )
        )
    for n in nodes:
        for ch in n.children:
            if 0 <= ch < len(nodes):
                nodes[ch].parent = n.index
    roots = [n.index for n in nodes if n.parent == -1]

    # 2. Skins (inverseBindMatrices em forma matemática padrão com translação na coluna 3)
    skins: list[VrmSkin] = []
    for sk in gltf.get("skins", []):
        joints = list(sk.get("joints", []))
        if "inverseBindMatrices" in sk:
            ibm_raw = _read_accessor(gltf, bin_chunk, sk["inverseBindMatrices"]).astype(np.float32)
            ibm = np.transpose(ibm_raw.reshape((len(joints), 4, 4)), (0, 2, 1)).copy()
        else:
            ibm = np.repeat(np.eye(4, dtype=np.float32)[None, :, :], len(joints), axis=0)
        skins.append(VrmSkin(joints=joints, inv_bind_matrices=ibm))

    # 3. Texturas & Materiais (com suporte a MToon shadeColor)
    tex_cache: dict[int, np.ndarray | None] = {}
    textures = gltf.get("textures", [])
    vrm_ext = gltf.get("extensions", {})
    vrm0_mats = {
        m.get("name", ""): m
        for m in (vrm_ext.get("VRM", {}).get("materialProperties", []) or [])
    }

    materials: list[VrmMaterial] = []
    for idx, m in enumerate(gltf.get("materials", [])):
        mname = str(m.get("name", f"mat_{idx}"))
        pbr = m.get("pbrMetallicRoughness", {})
        bc = tuple(float(x) for x in pbr.get("baseColorFactor", [1.0, 1.0, 1.0, 1.0]))
        tex_rgba = None
        if "baseColorTexture" in pbr:
            t_idx = int(pbr["baseColorTexture"]["index"])
            if 0 <= t_idx < len(textures):
                src_idx = textures[t_idx].get("source")
                if src_idx is not None:
                    if src_idx not in tex_cache:
                        tex_cache[src_idx] = _decode_image_rgba(gltf, bin_chunk, int(src_idx))
                    tex_rgba = tex_cache[src_idx]

        # Cor de sombra MToon (VRM 1.0 VRMC_materials_mtoon ou VRM 0.x materialProperties)
        shade = (0.82, 0.78, 0.86)
        mtoon1 = m.get("extensions", {}).get("VRMC_materials_mtoon")
        if isinstance(mtoon1, dict) and "shadeColorFactor" in mtoon1:
            sc = mtoon1["shadeColorFactor"]
            shade = (float(sc[0]), float(sc[1]), float(sc[2]))
        elif mname in vrm0_mats:
            sc = vrm0_mats[mname].get("vectorProperties", {}).get("_ShadeColor")
            if sc and len(sc) >= 3:
                shade = (float(sc[0]), float(sc[1]), float(sc[2]))

        materials.append(
            VrmMaterial(
                index=idx,
                name=mname,
                role=_classify_material_role(mname),
                base_color=(bc[0], bc[1], bc[2], bc[3] if len(bc) > 3 else 1.0),
                shade_color=shade,
                texture_rgba=tex_rgba,
                alpha_mode=str(m.get("alphaMode", "OPAQUE")),
                alpha_cutoff=float(m.get("alphaCutoff", 0.5)),
                double_sided=bool(m.get("doubleSided", False)),
            )
        )

    # 4. Primitivas de malha vinculadas aos nós de cena (mesh + skin)
    primitives: list[VrmPrimitive] = []
    min_y, max_y = 1e9, -1e9
    raw_meshes = gltf.get("meshes", [])
    mesh_node_pairs: list[tuple[int, int]] = []
    for n in nodes:
        if n.mesh >= 0:
            mesh_node_pairs.append((n.mesh, n.skin))
    if not mesh_node_pairs:
        mesh_node_pairs = [(i, -1) for i in range(len(raw_meshes))]

    for mesh_idx, skin_idx in mesh_node_pairs:
        m = raw_meshes[mesh_idx]
        for prim in m.get("primitives", []):
            attrs = prim.get("attributes", {})
            if "POSITION" not in attrs:
                continue
            pos = _read_accessor(gltf, bin_chunk, attrs["POSITION"]).astype(np.float32)
            vcount = pos.shape[0]
            if vcount == 0:
                continue
            min_y = min(min_y, float(pos[:, 1].min()))
            max_y = max(max_y, float(pos[:, 1].max()))

            if "NORMAL" in attrs:
                norm = _read_accessor(gltf, bin_chunk, attrs["NORMAL"]).astype(np.float32)
            else:
                norm = np.tile(np.array([[0.0, 0.0, 1.0]], dtype=np.float32), (vcount, 1))

            if "TEXCOORD_0" in attrs:
                uv = _read_accessor(gltf, bin_chunk, attrs["TEXCOORD_0"]).astype(np.float32)
            else:
                uv = np.zeros((vcount, 2), dtype=np.float32)

            if "JOINTS_0" in attrs and "WEIGHTS_0" in attrs and skin_idx >= 0:
                joints = _read_accessor(gltf, bin_chunk, attrs["JOINTS_0"]).astype(np.float32)
                weights = _read_accessor(gltf, bin_chunk, attrs["WEIGHTS_0"]).astype(np.float32)
                wsum = weights.sum(axis=1, keepdims=True)
                weights = np.where(wsum > 1e-5, weights / np.maximum(wsum, 1e-5), np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
            else:
                joints = np.zeros((vcount, 4), dtype=np.float32)
                weights = np.tile(np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32), (vcount, 1))

            if "indices" in prim:
                indices = _read_accessor(gltf, bin_chunk, prim["indices"]).astype(np.uint32).reshape(-1)
            else:
                indices = np.arange(vcount, dtype=np.uint32)

            morphs: list[np.ndarray] = []
            for tgt in prim.get("targets", []):
                if "POSITION" in tgt:
                    morphs.append(_read_accessor(gltf, bin_chunk, tgt["POSITION"]).astype(np.float32))
                else:
                    morphs.append(np.zeros((vcount, 3), dtype=np.float32))

            primitives.append(
                VrmPrimitive(
                    mesh_index=mesh_idx,
                    skin_index=skin_idx,
                    material_index=int(prim.get("material", 0)),
                    positions=pos,
                    normals=norm,
                    uvs=uv,
                    joints=joints,
                    weights=weights,
                    indices=indices,
                    morph_deltas=morphs,
                )
            )

    # 5. Metadados VRM 1.0 ou VRM 0.x (humanoid bones, expressões, spring bones)
    is_vrm1 = "VRMC_vrm" in vrm_ext
    model_name = path.stem
    humanoid_bones: dict[str, int] = {}
    expressions: dict[str, list[tuple[int, int, float]]] = {}
    springs: list[VrmSpringChain] = []

    if is_vrm1:
        v1 = vrm_ext["VRMC_vrm"]
        model_name = str(v1.get("meta", {}).get("name") or model_name)
        for bname, binfo in (v1.get("humanoid", {}).get("humanBones", {}) or {}).items():
            if isinstance(binfo, dict) and "node" in binfo:
                humanoid_bones[bname] = int(binfo["node"])
        presets = v1.get("expressions", {}).get("preset", {}) or {}
        for ename, einfo in presets.items():
            binds: list[tuple[int, int, float]] = []
            for b in einfo.get("morphTargetBinds", []) or []:
                node_i = int(b["node"])
                mesh_i = nodes[node_i].mesh if 0 <= node_i < len(nodes) else -1
                if mesh_i >= 0:
                    binds.append((mesh_i, int(b["index"]), float(b.get("weight", 1.0))))
            if binds:
                expressions[ename.lower()] = binds
        sp_ext = vrm_ext.get("VRMC_springBone", {})
        sp_joints = sp_ext.get("joints", []) or []
        for sp in sp_ext.get("springs", []) or []:
            j_nodes: list[int] = []
            stiff, drag, grav = 1.0, 0.45, 0.12
            for ji in sp.get("joints", []) or []:
                jd = ji if isinstance(ji, dict) else (sp_joints[ji] if isinstance(ji, int) and 0 <= ji < len(sp_joints) else None)
                if isinstance(jd, dict) and "node" in jd:
                    j_nodes.append(int(jd["node"]))
                    stiff = float(jd.get("stiffness", stiff))
                    drag = float(jd.get("dragForce", drag))
                    grav = float(jd.get("gravityPower", grav))
            if len(j_nodes) >= 2:
                springs.append(VrmSpringChain(joints=j_nodes, stiffness=stiff, drag=drag, gravity_power=grav))
    elif "VRM" in vrm_ext:
        v0 = vrm_ext["VRM"]
        model_name = str(v0.get("meta", {}).get("title") or model_name)
        for binfo in v0.get("humanoid", {}).get("humanBones", []) or []:
            bname = binfo.get("bone")
            if bname and "node" in binfo:
                humanoid_bones[str(bname)] = int(binfo["node"])
        for bg in v0.get("blendShapeMaster", {}).get("blendShapeGroups", []) or []:
            ename = str(bg.get("presetName") or bg.get("name") or "").lower()
            # Mapeia nomes VRM 0.x -> canônicos VRM 1.0
            alias = {"joy": "happy", "fun": "relaxed", "sorrow": "sad", "blink_l": "blinkleft", "blink_r": "blinkright"}.get(ename, ename)
            binds = []
            for b in bg.get("binds", []) or []:
                binds.append((int(b["mesh"]), int(b["index"]), float(b.get("weight", 100.0)) / 100.0))
            if alias and binds:
                expressions[alias] = binds
        for grp in v0.get("secondaryAnimation", {}).get("boneGroups", []) or []:
            stiff = float(grp.get("stiffiness", grp.get("stiffness", 1.0)))
            drag = float(grp.get("dragForce", 0.4))
            grav = float(grp.get("gravityPower", 0.12))
            for root_b in grp.get("bones", []) or []:
                chain = [int(root_b)]
                cur = int(root_b)
                while 0 <= cur < len(nodes) and nodes[cur].children:
                    cur = nodes[cur].children[0]
                    chain.append(cur)
                if len(chain) >= 2:
                    springs.append(VrmSpringChain(joints=chain, stiffness=stiff, drag=drag, gravity_power=grav))

    # 6. Restrições VRM 1.0 (`VRMC_node_constraint`: aim / roll / rotation — mangas, ombros, shorts/saia!)
    constraints: list[VrmConstraint] = []
    for idx, rn in enumerate(raw_nodes):
        nc = rn.get("extensions", {}).get("VRMC_node_constraint", {}).get("constraint", {})
        if not isinstance(nc, dict):
            continue
        if "aim" in nc:
            a = nc["aim"]
            constraints.append(VrmConstraint(idx, "aim", int(a["source"]), str(a.get("aimAxis", "PositiveX")), float(a.get("weight", 1.0))))
        elif "roll" in nc:
            r = nc["roll"]
            constraints.append(VrmConstraint(idx, "roll", int(r["source"]), str(r.get("rollAxis", "X")), float(r.get("weight", 1.0))))
        elif "rotation" in nc:
            rot = nc["rotation"]
            constraints.append(VrmConstraint(idx, "rotation", int(rot["source"]), "", float(rot.get("weight", 1.0))))

    height = max(0.5, max_y - min_y) if max_y > min_y else 1.60
    return VrmModel(
        name=model_name,
        is_vrm1=is_vrm1,
        nodes=nodes,
        roots=roots,
        skins=skins,
        materials=materials,
        primitives=primitives,
        humanoid_bones=humanoid_bones,
        expressions=expressions,
        springs=springs,
        constraints=constraints,
        height=height,
        min_y=min_y if min_y < 1e8 else 0.0,
    )
