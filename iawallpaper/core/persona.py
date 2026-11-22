"""PERSONA — Definição de personagens waifu (temperamento neural, paleta visual, trajes e sussurros)."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re

from ..store import read_json, write_json


TEMPERAMENT_PRESETS: dict[str, dict[str, float]] = {
    "cozy": {
        "CARESS": 1.25, "RAIN": 1.25, "NIGHT": 1.15, "MUSIC": 1.15, "WORK": 1.10, "DISMISS": 0.80,
    },
    "playful": {
        "PLAY": 1.30, "POKE": 1.25, "CARESS": 1.20, "MUSIC": 1.20, "NOVELTY": 1.25,
    },
    "focused": {
        "WORK": 1.35, "AI_CRAFT": 1.30, "TYPING": 1.20, "CARESS": 1.10, "DISMISS": 0.90,
    },
    "night_owl": {
        "NIGHT": 1.35, "STORM": 1.20, "MUSIC": 1.25, "PLAY": 1.20, "AI_CRAFT": 1.25,
    },
}


@dataclass
class Persona:
    id: str
    name: str
    title: str
    bio: str
    seed: int
    hair_color: tuple[int, int, int]
    hair_highlight: tuple[int, int, int]
    eye_color: tuple[int, int, int]
    skin_color: tuple[int, int, int]
    accent_color: tuple[int, int, int]
    temperament: dict[str, float] = field(default_factory=dict)
    comfy_character_tags: str = ""
    outfits: dict[str, dict] = field(default_factory=dict)
    whispers: dict[str, list[str]] = field(default_factory=dict)


BUILTIN_PERSONAS: dict[str, Persona] = {
    "mira": Persona(
        id="mira",
        name="Mira",
        title="Guardiã do Observatório Celeste",
        bio="Companheira anime serena, curiosa e carinhosa que adora noites estreladas, chuva na janela e acompanhar suas sessões de código e criação.",
        seed=2026,
        hair_color=(56, 62, 118),
        hair_highlight=(140, 165, 255),
        eye_color=(115, 205, 255),
        skin_color=(255, 232, 222),
        accent_color=(122, 184, 255),
        temperament={
            "CARESS": 1.20,
            "WORK": 1.15,
            "AI_CRAFT": 1.25,
            "RAIN": 1.25,
            "NIGHT": 1.15,
            "MUSIC": 1.10,
            "DISMISS": 0.85,
        },
        comfy_character_tags=(
            "1girl, solo, anime_style, masterpiece, best_quality, "
            "long_indigo_hair, starry_hair_ornament, bright_cyan_eyes, gentle_smile, "
            "delicate_features, soft_shading, upper_body, looking_at_viewer"
        ),
        outfits={
            "casual": {
                "label": "Cardigã Celeste",
                "primary": (76, 98, 168),
                "secondary": (235, 240, 252),
                "trim": (150, 210, 255),
                "prompt": "cozy_cream_cardigan, pleated_skirt, sky_blue_ribbon, casual_anime_outfit",
            },
            "focus": {
                "label": "Estúdio & Óculos",
                "primary": (48, 56, 86),
                "secondary": (240, 242, 248),
                "trim": (110, 220, 255),
                "prompt": "stylish_round_glasses, white_shirt, dark_navy_vest, relaxed_tie, studious_look",
            },
            "rainy": {
                "label": "Moletom de Chuva",
                "primary": (88, 138, 178),
                "secondary": (222, 242, 255),
                "trim": (180, 235, 255),
                "prompt": "oversized_pastel_blue_hoodie, cozy_rainy_day_outfit, soft_scarf",
            },
            "cozy": {
                "label": "Suéter Aconchegante",
                "primary": (162, 108, 134),
                "secondary": (250, 236, 230),
                "trim": (255, 198, 175),
                "prompt": "warm_knitted_sweater, soft_amber_lights, cozy_aesthetic",
            },
            "nightwear": {
                "label": "Pijama Estrelado",
                "primary": (62, 54, 110),
                "secondary": (218, 212, 252),
                "trim": (255, 226, 145),
                "prompt": "silk_starlight_pajamas, sleepy_cozy_look, moon_hairpin",
            },
            "starlight": {
                "label": "Vestido Astral",
                "primary": (44, 52, 128),
                "secondary": (195, 225, 255),
                "trim": (255, 228, 140),
                "prompt": "elegant_starry_night_dress, glowing_celestial_accents, dreamy_aura",
            },
        },
        whispers={
            "greet": [
                "Bem-vindo de volta! Estava observando o céu esperando você.",
                "Oi! Que bom te ver por aqui de novo ✨",
                "Voltou! O cenário fica bem mais vivo com você aqui.",
            ],
            "caress": [
                "Hehe... isso é tão quentinho ♥",
                "Fico tão calma quando você faz carinho assim...",
                "Vou guardar esse momento na minha memória ✨",
            ],
            "work": [
                "Foco total! Vou ficar aqui quietinha torcendo por você.",
                "Programando firme hoje? Não esquece de beber água!",
                "Adoro ver suas ideias ganhando forma na tela.",
            ],
            "ai_craft": [
                "O ComfyUI está trabalhando duro! O que estamos criando hoje?",
                "Senti a GPU aquecendo... arte nova vindo aí! ✨",
            ],
            "rain": [
                "A chuva lá fora deixa tudo tão aconchegante...",
                "Som de chuva e luz suave... clima perfeito para relaxar.",
            ],
            "storm": [
                "Nossa, que relâmpago! Ainda bem que estamos abrigados aqui.",
                "O céu está agitado lá fora... fica pertinho.",
            ],
            "night": [
                "As estrelas apareceram... não vai virar a noite sem descansar, hein?",
                "A madrugada está linda hoje. Se bater o sono, eu cuido do desktop.",
            ],
            "music": [
                "Essa trilha combina direitinho com o clima daqui ♪",
                "Boa música muda toda a energia do cenário ♪",
            ],
            "gaming": [
                "Boa sorte na partida! Vou pausar quietinha pra não gastar sua GPU.",
                "Vai com tudo no jogo! Depois me conta como foi ✨",
            ],
            "sleepy": [
                "Mmm... minhas pálpebras estão ficando pesadas... Zzz",
                "Vou tirar um cochilo rapidinho sob as estrelas...",
            ],
            "pout": [
                "Ei... faz um tempinho que você não fala comigo...",
                "Hmmpf... um carinho rapidinho já me fazia sorrir.",
            ],
            "idle": [
                "Olha como a luz mudou no horizonte...",
                "Estou aprendendo o seu ritmo aos poucos ✨",
                "Se quiser mudar meu visual ou o clima, é só abrir a Central.",
            ],
        },
    ),
    "nyx": Persona(
        id="nyx",
        name="Nyx",
        title="Operadora Neon da Madrugada",
        bio="Personalidade espirituosa, notívaga e tecnológica. Ama música, jogos, luzes cyberpunk e acompanha projetos criativos com bom humor.",
        seed=7777,
        hair_color=(188, 68, 148),
        hair_highlight=(255, 145, 225),
        eye_color=(255, 196, 88),
        skin_color=(252, 228, 222),
        accent_color=(244, 114, 182),
        temperament={
            "PLAY": 1.30,
            "MUSIC": 1.25,
            "NIGHT": 1.30,
            "AI_CRAFT": 1.20,
            "POKE": 1.20,
            "CARESS": 1.10,
            "STORM": 1.15,
        },
        comfy_character_tags=(
            "1girl, solo, anime_style, masterpiece, best_quality, "
            "magenta_pink_hair, glowing_amber_eyes, playful_smirk, techwear_choker, "
            "cyberpunk_accent_lighting, upper_body, looking_at_viewer"
        ),
        outfits={
            "casual": {
                "label": "Jaqueta Neon",
                "primary": (42, 34, 62),
                "secondary": (244, 114, 182),
                "trim": (56, 228, 255),
                "prompt": "stylish_dark_techwear_jacket, neon_pink_trim, modern_streetwear",
            },
            "focus": {
                "label": "Modo Dev Cyber",
                "primary": (34, 38, 58),
                "secondary": (90, 240, 220),
                "trim": (255, 120, 200),
                "prompt": "sleek_visor_glasses, dark_turtleneck, glowing_cyan_accents",
            },
            "rainy": {
                "label": "Capa Translúcida",
                "primary": (58, 72, 118),
                "secondary": (150, 235, 255),
                "trim": (255, 140, 210),
                "prompt": "cyberpunk_rain_jacket, neon_reflections, hood_down",
            },
            "cozy": {
                "label": "Hoodie Lo-Fi",
                "primary": (118, 58, 108),
                "secondary": (255, 224, 238),
                "trim": (255, 192, 118),
                "prompt": "oversized_lofi_hoodie, headphones_around_neck, warm_glow",
            },
            "nightwear": {
                "label": "Camisa Oversized",
                "primary": (54, 42, 82),
                "secondary": (245, 205, 235),
                "trim": (180, 150, 255),
                "prompt": "cozy_oversized_night_shirt, relaxed_sleepy_look",
            },
            "starlight": {
                "label": "Gala Synthwave",
                "primary": (78, 32, 108),
                "secondary": (255, 148, 220),
                "trim": (110, 235, 255),
                "prompt": "glamorous_synthwave_dress, holographic_shimmer, evening_glow",
            },
        },
        whispers={
            "greet": [
                "E aí, chefe! Desktop pronto pra ação ⚡",
                "Voltou! Achei que tinha me deixado sozinha com os ícones.",
            ],
            "caress": [
                "Ei... não estraga meu cabelo! ...tá, pode continuar ♥",
                "Hehe, sabe exatamente como ganhar pontos comigo.",
            ],
            "work": [
                "Codando no modo turbo? Deixa que eu mantenho a vibe lá em cima.",
                "Se compilar de primeira, eu mereço um carinho extra!",
            ],
            "ai_craft": [
                "GPU cantando no ComfyUI! Quero ver esse resultado depois ⚡",
            ],
            "rain": [
                "Chuva + neon = estética imbatível.",
            ],
            "storm": [
                "Relâmpago ao vivo no cenário! Esse wallpaper tá vivo mesmo ⚡",
            ],
            "night": [
                "A madrugada é oficialmente o nosso horário nobre.",
            ],
            "music": [
                "Aumenta o som! A energia daqui acabou de subir ♪",
            ],
            "gaming": [
                "GG! Vou entrar em modo econômico enquanto você joga.",
            ],
            "sleepy": [
                "Bateria em 15%... entrando em modo standby... Zzz",
            ],
            "pout": [
                "Alôôô? Tem uma waifu carente no seu papel de parede!",
            ],
            "idle": [
                "Monitorando o horizonte e aprendendo seus hábitos ⚡",
                "Clica na bandeja quando quiser brincar com os controles!",
            ],
        },
    ),
}


def list_personas(personas_dir: Path | None = None) -> list[str]:
    names = set(BUILTIN_PERSONAS.keys())
    if personas_dir and personas_dir.exists():
        for f in personas_dir.glob("*.json"):
            names.add(f.stem.lower())
    return sorted(names)


def load_persona(persona_id: str, personas_dir: Path | None = None) -> Persona:
    pid = (persona_id or "mira").strip().lower()
    if personas_dir:
        custom_file = personas_dir / f"{pid}.json"
        if custom_file.exists():
            raw = read_json(custom_file, default=None)
            if isinstance(raw, dict):
                base = BUILTIN_PERSONAS.get("mira")
                return Persona(
                    id=pid,
                    name=str(raw.get("name", pid.title())),
                    title=str(raw.get("title", "Companheira Dinâmica")),
                    bio=str(raw.get("bio", "")),
                    seed=int(raw.get("seed", 2026)),
                    hair_color=tuple(raw.get("hair_color", base.hair_color)),
                    hair_highlight=tuple(raw.get("hair_highlight", base.hair_highlight)),
                    eye_color=tuple(raw.get("eye_color", base.eye_color)),
                    skin_color=tuple(raw.get("skin_color", base.skin_color)),
                    accent_color=tuple(raw.get("accent_color", base.accent_color)),
                    temperament=dict(raw.get("temperament", {})),
                    comfy_character_tags=str(raw.get("comfy_character_tags", base.comfy_character_tags)),
                    outfits=dict(raw.get("outfits", base.outfits)),
                    whispers=dict(raw.get("whispers", base.whispers)),
                )
    return BUILTIN_PERSONAS.get(pid, BUILTIN_PERSONAS["mira"])


def slugify_persona_id(name: str) -> str:
    """Normaliza um nome escolhido pelo usuário em um persona_id seguro."""
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return slug[:28] or "custom_waifu"


def create_custom_persona(
    name: str,
    title: str,
    character_tags: str,
    temperament_preset: str = "cozy",
    hair_color: tuple[int, int, int] = (72, 68, 128),
    eye_color: tuple[int, int, int] = (120, 205, 255),
    accent_color: tuple[int, int, int] = (145, 190, 255),
    seed: int | None = None,
) -> Persona:
    """Cria uma persona waifu personalizada completa com os 6 trajes dinâmicos e sussurros."""
    base = BUILTIN_PERSONAS["mira"]
    pid = slugify_persona_id(name)
    actual_seed = int(seed if seed is not None else (abs(hash(pid)) % 900000 + 1000))
    tags = (character_tags or "").strip()
    if "1girl" not in tags.lower():
        tags = f"1girl, solo, anime_style, masterpiece, best_quality, {tags}, upper_body, looking_at_viewer"
    return Persona(
        id=pid,
        name=(name or "Nova Waifu").strip(),
        title=(title or "Companheira Personalizada").strip(),
        bio=f"Persona personalizada criada no IAWallpaper Studio ({temperament_preset}).",
        seed=actual_seed,
        hair_color=hair_color,
        hair_highlight=tuple(min(255, c + 65) for c in hair_color),
        eye_color=eye_color,
        skin_color=base.skin_color,
        accent_color=accent_color,
        temperament=dict(TEMPERAMENT_PRESETS.get(temperament_preset, TEMPERAMENT_PRESETS["cozy"])),
        comfy_character_tags=tags,
        outfits=dict(base.outfits),
        whispers=dict(base.whispers),
    )


def save_persona(persona: Persona, personas_dir: Path) -> Path:
    """Persiste uma persona personalizada em assets/personas/<id>.json atomicamente."""
    personas_dir.mkdir(parents=True, exist_ok=True)
    out = personas_dir / f"{persona.id}.json"
    data = asdict(persona)
    write_json(out, data, indent=2)
    return out
