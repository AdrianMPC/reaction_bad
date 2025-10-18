import os, time, random, math
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client, Client

# =======================
# Carga .env y helpers
# =======================
load_dotenv()

def getenv_any(*keys, default=""):
    for k in keys:
        v = os.getenv(k)
        if v and v.strip():
            return v.strip()
    return default

SUPABASE_URL      = getenv_any("SUPABASE_URL", "supabase_url")
SUPABASE_ANON_KEY = getenv_any("SUPABASE_ANON_KEY", "supabase_anon_key")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError(
        "Faltan SUPABASE_URL / SUPABASE_ANON_KEY (o en minúsculas). "
        "Completa tu archivo .env."
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# =======================
# Config & categorías
# =======================
st.set_page_config(page_title="Test de Reacción", page_icon="⚡", layout="centered")
st.title("⚡ Test de Reacción (5 intentos)")
st.caption("Conectado a Supabase con anon key.")

CATEGORIES = [
    ("Superhumano", 100),
    ("Gamer pro", 150),
    ("Muy rápido", 200),
    ("Promedio humano", 250),
    ("Lento", 350),
    ("¿Todo bien?", math.inf),
]

def category_for(avg_ms: float) -> str:
    for label, thr in CATEGORIES:
        if avg_ms <= thr:
            return label
    return "N/A"

# =======================
# Estado
# =======================
player_name = st.text_input("Tu nombre (para el ranking)", max_chars=80)

if "attempts" not in st.session_state:
    st.session_state.attempts = []  # lista de tiempos en ms
if "phase" not in st.session_state:
    st.session_state.phase = "idle"  # idle -> waiting -> ready
if "target_time" not in st.session_state:
    st.session_state.target_time = None
if "delay_ms" not in st.session_state:
    st.session_state.delay_ms = None

# =======================
# Instrucciones y métricas
# =======================
st.markdown("""
**Instrucciones**  
1) Pulsa **Iniciar intento**.  
2) Espera a que el botón cambie a **¡Haz clic ahora!** (tarda 1–4 s).  
3) Haz clic lo más rápido posible.  
4) Realiza **5 intentos** para obtener tu promedio y entrar al ranking.  
""")

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Intentos hechos", f"{len(st.session_state.attempts)}/5")
with c2:
    st.metric("Último (ms)", f"{st.session_state.attempts[-1]:.0f}" if st.session_state.attempts else "-")
with c3:
    if st.session_state.attempts:
        st.metric("Promedio parcial", f"{sum(st.session_state.attempts)/len(st.session_state.attempts):.1f} ms")
    else:
        st.metric("Promedio parcial", "-")

st.divider()

# =======================
# Flujo de intentos
# =======================
if len(st.session_state.attempts) < 5:
    if st.session_state.phase == "idle":
        if st.button("Iniciar intento", type="primary", use_container_width=True, disabled=not player_name):
            st.session_state.delay_ms = random.randint(1000, 4000)  # 1–4 s
            st.session_state.phase = "waiting"
            st.rerun()

    elif st.session_state.phase == "waiting":
        st.info("⏳ Espera… El botón aparecerá en breve. ¡No hagas clic aún!")
        time.sleep(st.session_state.delay_ms / 1000.0)
        st.session_state.target_time = time.time()
        st.session_state.phase = "ready"
        st.rerun()

    elif st.session_state.phase == "ready":
        clicked = st.button("¡Haz clic ahora!", type="primary", use_container_width=True)
        if clicked:
            rt_ms = (time.time() - st.session_state.target_time) * 1000.0
            st.session_state.attempts.append(round(max(1.0, rt_ms), 2))
            st.session_state.phase = "idle"
            st.session_state.target_time = None
            st.session_state.delay_ms = None
            st.rerun()

else:
    # =======================
    # Resultados y persistencia
    # =======================
    attempts = st.session_state.attempts
    avg_ms = sum(attempts) / 5.0
    label = category_for(avg_ms)

    st.success(f"✅ ¡Listo {player_name}! Tu **promedio** es **{avg_ms:.1f} ms** → **{label}**")
    st.write(f"Intentos (ms): {', '.join(str(int(x)) for x in attempts)}")

    if st.button("Guardar resultado y ver Top 10", type="primary", use_container_width=True):
        try:
            payload = {
                "player_name": player_name.strip(),
                "attempt1_ms": int(round(attempts[0])),
                "attempt2_ms": int(round(attempts[1])),
                "attempt3_ms": int(round(attempts[2])),
                "attempt4_ms": int(round(attempts[3])),
                "attempt5_ms": int(round(attempts[4])),
            }
            # Insert (average_ms es columna generada en la BD)
            supabase.table("reaction_tests").insert(payload).execute()
            st.toast("Guardado en Supabase ✅", icon="✅")

            # Leaderboard vía RPC (recomendado: función get_reaction_leaderboard del SQL)
            top_rows = []
            try:
                resp = supabase.rpc("get_reaction_leaderboard", {"limit_count": 10}).execute()
                top_rows = resp.data or []
            except Exception:
                # Fallback sólo si tu RLS permite SELECT a la tabla
                resp = (
                    supabase.table("reaction_tests")
                    .select("player_name, average_ms, created_at")
                    .order("average_ms", desc=False)
                    .order("created_at", desc=False)
                    .limit(10)
                    .execute()
                )
                top_rows = resp.data or []

            if top_rows:
                st.subheader("🏆 Top 10 más rápidos")
                for i, row in enumerate(top_rows, start=1):
                    pname = row.get("player_name", "—")
                    avg = row.get("average_ms", None)
                    created_at = row.get("created_at", "")
                    avg_str = f"{float(avg):.1f} ms" if avg is not None else "s/d"
                    st.write(f"**{i}. {pname}** — {avg_str} · {created_at}")
            else:
                st.warning("No hay datos para el Top 10 todavía.")
        except Exception as e:
            st.error(f"Error al guardar/obtener ranking: {e}")

    if st.button("Volver a intentar (reiniciar)"):
        st.session_state.attempts = []
        st.session_state.phase = "idle"
        st.session_state.target_time = None
        st.session_state.delay_ms = None
        st.rerun()

st.caption("Tip: valores humanos típicos ~180–300 ms. ¡Intenta superarte!")
