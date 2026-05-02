"""
Generate handwritten-style JEE test images for pipeline testing.
Creates question + answer image pairs with known correct/incorrect answers.
"""

import json
import os
import random
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).parent / "test_images"
MANIFEST = OUT_DIR / "manifest.json"

# Handwriting-style fonts on macOS
FONTS = [
    "/System/Library/Fonts/MarkerFelt.ttc",
    "/System/Library/Fonts/Noteworthy.ttc",
]

# Slight color variations to simulate pen types
INK_COLORS = [
    (20, 20, 80),     # dark blue
    (10, 10, 10),     # near-black
    (40, 10, 10),     # dark red-brown
    (0, 0, 120),      # blue pen
    (30, 30, 30),     # pencil grey
]

# Paper background colors
PAPER_COLORS = [
    (255, 255, 250),  # white
    (255, 253, 240),  # slight yellow
    (248, 248, 255),  # slight blue tint
    (255, 250, 240),  # floral white
]

# ────────────────────────────────────────────────────────────────
# TEST CASES: 15 per subject, mix of easy/medium/hard, some wrong
# ────────────────────────────────────────────────────────────────

MATHS_PROBLEMS = [
    # Easy (5)
    {
        "id": "m01", "difficulty": "easy", "topic": "Quadratics",
        "question": "Solve: x² - 5x + 6 = 0",
        "student_work": "x^2 - 5x + 6 = 0\n(x - 2)(x - 3) = 0\nx = 2 or x = 3",
        "is_correct": True, "correct_answer": "x = 2 or x = 3",
        "expected_score_min": 4,
    },
    {
        "id": "m02", "difficulty": "easy", "topic": "Trigonometry",
        "question": "Find the value of sin²θ + cos²θ",
        "student_work": "sin^2(theta) + cos^2(theta)\n= 1 (Pythagorean identity)",
        "is_correct": True, "correct_answer": "1",
        "expected_score_min": 4,
    },
    {
        "id": "m03", "difficulty": "easy", "topic": "Matrices",
        "question": "Find determinant of [[2,3],[1,4]]",
        "student_work": "det = 2×4 - 3×1\n= 8 - 3\n= 5",
        "is_correct": True, "correct_answer": "5",
        "expected_score_min": 4,
    },
    {
        "id": "m04", "difficulty": "easy", "topic": "Calculus",
        "question": "Find dy/dx if y = x³ + 2x",
        "student_work": "dy/dx = 3x^2 + 2",
        "is_correct": True, "correct_answer": "3x² + 2",
        "expected_score_min": 4,
    },
    {
        "id": "m05", "difficulty": "easy", "topic": "Logarithms",
        "question": "Simplify: log₂(8)",
        "student_work": "log_2(8) = log_2(2^3)\n= 3 * log_2(2)\n= 3",
        "is_correct": True, "correct_answer": "3",
        "expected_score_min": 4,
    },
    # Medium (5) — 2 wrong
    {
        "id": "m06", "difficulty": "medium", "topic": "Integration",
        "question": "Evaluate: ∫ x² dx from 0 to 2",
        "student_work": "integral of x^2 dx = x^3/3\nFrom 0 to 2:\n= 2^3/3 - 0\n= 8/3",
        "is_correct": True, "correct_answer": "8/3",
        "expected_score_min": 4,
    },
    {
        "id": "m07", "difficulty": "medium", "topic": "Complex Numbers",
        "question": "Find |3 + 4i|",
        "student_work": "|3 + 4i| = sqrt(3^2 + 4^2)\n= sqrt(9 + 16)\n= sqrt(25)\n= 5",
        "is_correct": True, "correct_answer": "5",
        "expected_score_min": 4,
    },
    {
        "id": "m08", "difficulty": "medium", "topic": "Trigonometry",
        "question": "Find sin(π/6) + cos(π/3)",
        "student_work": "sin(pi/6) = 1/2\ncos(pi/3) = 1/2\nAnswer = 1/2 + 1/2 = 1",
        "is_correct": True, "correct_answer": "1",
        "expected_score_min": 4,
    },
    {
        "id": "m09", "difficulty": "medium", "topic": "Differentiation",
        "question": "Find dy/dx if y = sin(x²)",
        "student_work": "Using chain rule:\ndy/dx = cos(x^2) * x\n= x cos(x^2)",
        "is_correct": False, "correct_answer": "2x cos(x²)",
        "error": "Missing factor of 2 in chain rule — derivative of x² is 2x not x",
        "expected_score_min": 0, "expected_score_max": 3,
    },
    {
        "id": "m10", "difficulty": "medium", "topic": "Probability",
        "question": "Two dice are thrown. P(sum = 7)?",
        "student_work": "Favorable: (1,6)(2,5)(3,4)(4,3)(5,2)(6,1)\n= 6 outcomes\nTotal = 36\nP = 6/36 = 1/3",
        "is_correct": False, "correct_answer": "1/6",
        "error": "6/36 = 1/6 not 1/3",
        "expected_score_min": 1, "expected_score_max": 3,
    },
    # Hard (5) — 2 wrong
    {
        "id": "m11", "difficulty": "hard", "topic": "Integration",
        "question": "Evaluate: ∫ 1/(1+x²) dx from 0 to 1",
        "student_work": "integral 1/(1+x^2) dx = arctan(x) + C\nFrom 0 to 1:\n= arctan(1) - arctan(0)\n= pi/4 - 0 = pi/4",
        "is_correct": True, "correct_answer": "π/4",
        "expected_score_min": 4,
    },
    {
        "id": "m12", "difficulty": "hard", "topic": "Limits",
        "question": "Find lim(x→0) (sin x)/x",
        "student_work": "lim(x→0) sin(x)/x\n= 1 (standard limit)",
        "is_correct": True, "correct_answer": "1",
        "expected_score_min": 4,
    },
    {
        "id": "m13", "difficulty": "hard", "topic": "Matrices",
        "question": "Find inverse of A = [[1,2],[3,4]]",
        "student_work": "det(A) = 4-6 = -2\nA^-1 = (1/det) x [[4,-2],[-3,1]]\n= (-1/2)[[4,-2],[-3,1]]\n= [[-2, 1],[3/2, -1/2]]",
        "is_correct": True, "correct_answer": "[[-2, 1],[3/2, -1/2]]",
        "expected_score_min": 4,
    },
    {
        "id": "m14", "difficulty": "hard", "topic": "Differential Equations",
        "question": "Solve: dy/dx = y/x, y(1) = 2",
        "student_work": "dy/y = dx/x\nln|y| = ln|x| + C\ny = kx\ny(1)=2 → k=2\ny = 2x",
        "is_correct": True, "correct_answer": "y = 2x",
        "expected_score_min": 4,
    },
    {
        "id": "m15", "difficulty": "hard", "topic": "Binomial Theorem",
        "question": "Find coefficient of x³ in (1+x)⁷",
        "student_work": "C(7,3) x 1^4 x x^3\n= 7!/(3!4!)\n= 7x6x5/6\n= 210/6\n= 30",
        "is_correct": False, "correct_answer": "35",
        "error": "7×6×5 = 210, 210/6 = 35 not 30 — arithmetic error",
        "expected_score_min": 1, "expected_score_max": 3,
    },
]

PHYSICS_PROBLEMS = [
    # Easy (5)
    {
        "id": "p01", "difficulty": "easy", "topic": "Kinematics",
        "question": "A car accelerates from rest at 2 m/s². Find velocity after 5s.",
        "student_work": "u = 0, a = 2 m/s², t = 5s\nv = u + at\nv = 0 + 2×5\nv = 10 m/s",
        "is_correct": True, "correct_answer": "10 m/s",
        "expected_score_min": 4,
    },
    {
        "id": "p02", "difficulty": "easy", "topic": "Newton's Laws",
        "question": "F = 20N, m = 4kg. Find acceleration.",
        "student_work": "F = ma\n20 = 4 × a\na = 20/4 = 5 m/s²",
        "is_correct": True, "correct_answer": "5 m/s²",
        "expected_score_min": 4,
    },
    {
        "id": "p03", "difficulty": "easy", "topic": "Work-Energy",
        "question": "Find KE of 2kg mass moving at 3 m/s",
        "student_work": "KE = (1/2)mv^2\n= (1/2)(2)(3^2)\n= (1/2)(2)(9)\n= 9 J",
        "is_correct": True, "correct_answer": "9 J",
        "expected_score_min": 4,
    },
    {
        "id": "p04", "difficulty": "easy", "topic": "Ohm's Law",
        "question": "V = 12V, R = 4Ω. Find current I.",
        "student_work": "V = IR\n12 = I x 4\nI = 12/4 = 3 A",
        "is_correct": True, "correct_answer": "3 A",
        "expected_score_min": 4,
    },
    {
        "id": "p05", "difficulty": "easy", "topic": "Waves",
        "question": "Find wavelength if v=340m/s, f=170Hz",
        "student_work": "v = f*lambda\nlambda = v/f = 340/170 = 2m",
        "is_correct": True, "correct_answer": "2 m",
        "expected_score_min": 4,
    },
    # Medium (5) — 2 wrong
    {
        "id": "p06", "difficulty": "medium", "topic": "Projectile Motion",
        "question": "Ball thrown up at 20m/s. Find max height. (g=10m/s²)",
        "student_work": "At max height, v=0\nv² = u² - 2gh\n0 = 400 - 20h\nh = 400/20 = 20m",
        "is_correct": True, "correct_answer": "20 m",
        "expected_score_min": 4,
    },
    {
        "id": "p07", "difficulty": "medium", "topic": "Electrostatics",
        "question": "Two charges +2μC and -3μC separated by 1m. Find force.",
        "student_work": "F = kq1q2/r^2\n= 9x10^9 x 2x10^-6 x 3x10^-6 / 1^2\n= 9x10^9 x 6x10^-12\n= 54x10^-3\n= 0.054 N",
        "is_correct": True, "correct_answer": "0.054 N (attractive)",
        "expected_score_min": 4,
    },
    {
        "id": "p08", "difficulty": "medium", "topic": "Thermodynamics",
        "question": "10g ice at 0°C to water at 0°C. Find heat needed. (L=80cal/g)",
        "student_work": "Q = mL\n= 10 × 80\n= 800 cal",
        "is_correct": True, "correct_answer": "800 cal",
        "expected_score_min": 4,
    },
    {
        "id": "p09", "difficulty": "medium", "topic": "Gravitation",
        "question": "At what height above Earth is g halved? (R=6400km)",
        "student_work": "g' = g/2\ng' = gR^2/(R+h)^2\nR^2/(R+h)^2 = 1/2\n(R+h)^2 = 2R^2\nR+h = R*sqrt(2)\nh = R(sqrt(2) - 1)\n= 6400 x 0.414\n= 2650 km",
        "is_correct": True, "correct_answer": "~2650 km",
        "expected_score_min": 4,
    },
    {
        "id": "p10", "difficulty": "medium", "topic": "Optics",
        "question": "Object at 30cm from concave mirror, f=20cm. Find image position.",
        "student_work": "1/v + 1/u = 1/f\n1/v + 1/(-30) = 1/(-20)\n1/v = -1/20 + 1/30\n1/v = (-3 + 2)/60 = -1/60\nv = -60 cm",
        "is_correct": True, "correct_answer": "v = -60 cm (real image)",
        "expected_score_min": 4,
    },
    # Hard (5) — 3 wrong
    {
        "id": "p11", "difficulty": "hard", "topic": "Rotational Motion",
        "question": "Moment of inertia of disc (M,R) about diameter?",
        "student_work": "I_disc about axis = MR^2/2\nBy perpendicular axis theorem:\nI_x + I_y = I_z\n2I_d = MR^2/2\nI_d = MR^2/4",
        "is_correct": True, "correct_answer": "MR²/4",
        "expected_score_min": 4,
    },
    {
        "id": "p12", "difficulty": "hard", "topic": "Electromagnetism",
        "question": "Find magnetic field at center of circular loop (radius R, current I)",
        "student_work": "B = mu_0 * I / (2R)",
        "is_correct": True, "correct_answer": "μ₀I/2R",
        "expected_score_min": 4,
    },
    {
        "id": "p13", "difficulty": "hard", "topic": "SHM",
        "question": "Time period of simple pendulum (L=1m, g=π²)",
        "student_work": "T = 2*pi*sqrt(L/g)\n= 2*pi*sqrt(1/pi^2)\n= 2*pi x 1/pi\n= 2 s",
        "is_correct": True, "correct_answer": "2 s",
        "expected_score_min": 4,
    },
    {
        "id": "p14", "difficulty": "hard", "topic": "Modern Physics",
        "question": "Energy of photon with wavelength 6600 Å",
        "student_work": "E = hc/lambda\n= (6.6x10^-34 x 3x10^8) / (6600x10^-10)\n= 19.8x10^-26 / 6.6x10^-7\n= 3x10^-19 J\n= 1.875 eV",
        "is_correct": True, "correct_answer": "~1.875 eV",
        "expected_score_min": 4,
    },
    {
        "id": "p15", "difficulty": "hard", "topic": "Kinematics",
        "question": "A ball is dropped from 80m. Find time to reach ground (g=10m/s²)",
        "student_work": "s = ut + (1/2)gt^2\n80 = 0 + (1/2)(10)t^2\n80 = 5t^2\nt^2 = 16\nt = 8 s",
        "is_correct": False, "correct_answer": "4 s",
        "error": "√16 = 4 not 8",
        "expected_score_min": 0, "expected_score_max": 3,
    },
]

CHEMISTRY_PROBLEMS = [
    # Easy (5)
    {
        "id": "c01", "difficulty": "easy", "topic": "Atomic Structure",
        "question": "How many electrons can the 3rd shell hold?",
        "student_work": "Max electrons in nth shell = 2n^2\n= 2(3)^2 = 2 x 9 = 18",
        "is_correct": True, "correct_answer": "18",
        "expected_score_min": 4,
    },
    {
        "id": "c02", "difficulty": "easy", "topic": "Balancing Equations",
        "question": "Balance: Fe + O₂ → Fe₂O₃",
        "student_work": "4Fe + 3O2 -> 2Fe2O3",
        "is_correct": True, "correct_answer": "4Fe + 3O₂ → 2Fe₂O₃",
        "expected_score_min": 4,
    },
    {
        "id": "c03", "difficulty": "easy", "topic": "Mole Concept",
        "question": "Moles in 36g of water (H₂O)?",
        "student_work": "Molar mass of H2O = 2+16 = 18 g/mol\nMoles = 36/18 = 2 mol",
        "is_correct": True, "correct_answer": "2 mol",
        "expected_score_min": 4,
    },
    {
        "id": "c04", "difficulty": "easy", "topic": "Periodic Table",
        "question": "Electronic config of Sodium (Z=11)",
        "student_work": "Na: 1s2 2s2 2p6 3s1\nor [Ne] 3s1",
        "is_correct": True, "correct_answer": "1s² 2s² 2p⁶ 3s¹",
        "expected_score_min": 4,
    },
    {
        "id": "c05", "difficulty": "easy", "topic": "pH",
        "question": "Find pH of 0.01 M HCl",
        "student_work": "HCl is strong acid, fully dissociates\n[H+] = 0.01 = 10^-2\npH = -log(10^-2) = 2",
        "is_correct": True, "correct_answer": "pH = 2",
        "expected_score_min": 4,
    },
    # Medium (5) — 2 wrong
    {
        "id": "c06", "difficulty": "medium", "topic": "Chemical Kinetics",
        "question": "Half-life of first order reaction with k=0.693 s⁻¹?",
        "student_work": "t_half = 0.693/k\n= 0.693/0.693\n= 1 s",
        "is_correct": True, "correct_answer": "1 s",
        "expected_score_min": 4,
    },
    {
        "id": "c07", "difficulty": "medium", "topic": "Organic Chemistry",
        "question": "IUPAC name of CH₃-CH₂-CH₂-OH",
        "student_work": "3-carbon chain with OH on carbon 1\n= Propan-1-ol",
        "is_correct": True, "correct_answer": "Propan-1-ol",
        "expected_score_min": 4,
    },
    {
        "id": "c08", "difficulty": "medium", "topic": "Thermochemistry",
        "question": "If ΔH = -286 kJ for H₂+½O₂→H₂O, is reaction exo or endo?",
        "student_work": "delta H is negative (-286 kJ)\nSo reaction releases heat\n-> Exothermic",
        "is_correct": True, "correct_answer": "Exothermic",
        "expected_score_min": 4,
    },
    {
        "id": "c09", "difficulty": "medium", "topic": "Electrochemistry",
        "question": "Find EMF: Zn|Zn²⁺||Cu²⁺|Cu (E°Zn=-0.76V, E°Cu=+0.34V)",
        "student_work": "E cell = E cathode - E anode\n= 0.34 - (-0.76)\n= 0.34 + 0.76\n= 1.00 V",
        "is_correct": False, "correct_answer": "1.10 V",
        "error": "0.34 + 0.76 = 1.10 not 1.00 — arithmetic error",
        "expected_score_min": 1, "expected_score_max": 3,
    },
    {
        "id": "c10", "difficulty": "medium", "topic": "Solutions",
        "question": "Molarity of 4g NaOH in 500ml solution? (Na=23,O=16,H=1)",
        "student_work": "Molar mass NaOH = 23+16+1 = 40\nMoles = 4/40 = 0.1\nVolume = 500ml = 0.5L\nM = 0.1/0.5 = 0.5 M",
        "is_correct": False, "correct_answer": "0.2 M",
        "error": "0.1/0.5 = 0.2 not 0.5 — division error",
        "expected_score_min": 0, "expected_score_max": 3,
    },
    # Hard (5) — 2 wrong
    {
        "id": "c11", "difficulty": "hard", "topic": "Chemical Equilibrium",
        "question": "For N₂+3H₂⇌2NH₃, write Kp expression",
        "student_work": "Kp = (p_NH3)^2 / (p_N2)(p_H2)^3",
        "is_correct": True, "correct_answer": "Kp = (p_NH₃)² / (p_N₂)(p_H₂)³",
        "expected_score_min": 4,
    },
    {
        "id": "c12", "difficulty": "hard", "topic": "Coordination Chemistry",
        "question": "Hybridization in [Fe(CN)₆]³⁻?",
        "student_work": "Fe3+: [Ar] 3d5\nCN- is strong field ligand -> pairing\nd2sp3 hybridization\n-> Octahedral, inner orbital complex",
        "is_correct": True, "correct_answer": "d²sp³",
        "expected_score_min": 4,
    },
    {
        "id": "c13", "difficulty": "hard", "topic": "Organic Chemistry",
        "question": "Major product of dehydration of 2-butanol?",
        "student_work": "CH3-CH(OH)-CH2-CH3\nE1 elimination -> Zaitsev's rule\nMajor product: But-2-ene (trans)",
        "is_correct": True, "correct_answer": "Trans-but-2-ene (Zaitsev product)",
        "expected_score_min": 4,
    },
    {
        "id": "c14", "difficulty": "hard", "topic": "Solid State",
        "question": "Number of atoms per unit cell in FCC?",
        "student_work": "Corner atoms: 8 × 1/8 = 1\nFace atoms: 6 × 1/2 = 3\nTotal = 1 + 3 = 4",
        "is_correct": True, "correct_answer": "4",
        "expected_score_min": 4,
    },
    {
        "id": "c15", "difficulty": "hard", "topic": "Ionic Equilibrium",
        "question": "Find pH of 0.1M CH₃COOH (Ka=1.8×10⁻⁵)",
        "student_work": "[H+] = sqrt(Ka x c)\n= sqrt(1.8x10^-5 x 0.1)\n= sqrt(1.8x10^-6)\n= 1.34x10^-3\npH = -log(1.34x10^-3)\n= 3 - log(1.34)\n= 3 - 0.13 = 2.87",
        "is_correct": True, "correct_answer": "~2.87",
        "expected_score_min": 4,
    },
]


def _pick_font(size=28):
    """Pick a random handwriting font."""
    path = random.choice(FONTS)
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _add_noise(img):
    """Add subtle imperfections to simulate real paper."""
    import random as rng
    draw = ImageDraw.Draw(img)
    w, h = img.size
    # Random dots (paper texture)
    for _ in range(rng.randint(5, 20)):
        x, y = rng.randint(0, w-1), rng.randint(0, h-1)
        c = rng.randint(200, 240)
        draw.point((x, y), fill=(c, c, c))
    return img


def _render_text_image(text, label="", width=800):
    """Render text onto a paper-like background image."""
    font = _pick_font(random.randint(24, 32))
    small_font = _pick_font(18)
    ink = random.choice(INK_COLORS)
    paper = random.choice(PAPER_COLORS)

    # Wrap text
    lines = []
    for raw_line in text.split("\n"):
        wrapped = textwrap.wrap(raw_line, width=50) or [""]
        lines.extend(wrapped)

    line_height = 40
    margin = 40
    height = margin * 2 + len(lines) * line_height + (60 if label else 0)
    height = max(height, 200)

    img = Image.new("RGB", (width, height), paper)
    draw = ImageDraw.Draw(img)

    y = margin
    if label:
        draw.text((margin, y), label, fill=(150, 150, 150), font=small_font)
        y += 40

    for line in lines:
        # Slight random offset to simulate handwriting wobble
        x_offset = random.randint(-2, 2)
        y_offset = random.randint(-1, 1)
        draw.text((margin + x_offset, y + y_offset), line, fill=ink, font=font)
        y += line_height

    _add_noise(img)
    return img


def generate_all():
    """Generate all test images and manifest."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_problems = {
        "maths": MATHS_PROBLEMS,
        "physics": PHYSICS_PROBLEMS,
        "chemistry": CHEMISTRY_PROBLEMS,
    }

    manifest = []

    for subject, problems in all_problems.items():
        for p in problems:
            pid = p["id"]

            # Generate question image
            q_img = _render_text_image(
                p["question"],
                label=f"Q{pid.upper()} — {subject.title()}"
            )
            q_path = OUT_DIR / f"{pid}_question.jpg"
            q_img.save(q_path, "JPEG", quality=85)

            # Generate answer image
            a_img = _render_text_image(
                p["student_work"],
                label=f"Answer — {pid.upper()}"
            )
            a_path = OUT_DIR / f"{pid}_answer.jpg"
            a_img.save(a_path, "JPEG", quality=85)

            manifest.append({
                "id": pid,
                "subject": subject,
                "difficulty": p["difficulty"],
                "topic": p["topic"],
                "question_file": f"{pid}_question.jpg",
                "answer_file": f"{pid}_answer.jpg",
                "is_correct": p["is_correct"],
                "correct_answer": p["correct_answer"],
                "error": p.get("error"),
                "expected_score_min": p.get("expected_score_min", 0),
                "expected_score_max": p.get("expected_score_max", 5),
            })

    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Generated {len(manifest)} test image pairs in {OUT_DIR}")
    print(f"Manifest: {MANIFEST}")

    # Summary
    for subj in ["maths", "physics", "chemistry"]:
        items = [m for m in manifest if m["subject"] == subj]
        correct = sum(1 for m in items if m["is_correct"])
        wrong = len(items) - correct
        print(f"  {subj}: {len(items)} problems ({correct} correct, {wrong} with errors)")


if __name__ == "__main__":
    generate_all()
