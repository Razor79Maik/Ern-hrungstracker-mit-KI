import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from google import genai
from google.genai import types

# --- 1. DATENBANK INITIALISIEREN ---
def init_db():
    conn = sqlite3.connect("nutrition_tracker.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            meal_type TEXT,
            description TEXT,
            calories INTEGER,
            protein REAL,
            carbs REAL,
            fat REAL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def save_meal(meal_type, description, calories, protein, carbs, fat):
    conn = sqlite3.connect("nutrition_tracker.db")
    c = conn.cursor()
    c.execute('''
        INSERT INTO meals (date, meal_type, description, calories, protein, carbs, fat)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (datetime.now().strftime("%Y-%m-%d"), meal_type, description, calories, protein, carbs, fat))
    conn.commit()
    conn.close()

def get_history():
    conn = sqlite3.connect("nutrition_tracker.db")
    df = pd.read_sql_query("SELECT * FROM meals ORDER BY id DESC", conn)
    conn.close()
    return df

# --- 2. GEMINI API SETUP ---
# Holt sich den API-Key sicher aus den Streamlit Secrets
api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

def analyze_food_image(image_bytes):
    prompt = """
    Analysiere dieses Bild von Essen. Schätze die Portionsgrößen und berechne die Nährwerte.
    Antworte AUSSCHLIESSLICH im folgenden JSON-Format, ohne Markdown-Formatierung (keine ```json Blöcke):
    {
        "description": "Kurze Beschreibung der erkannten Komponenten des Gerichts",
        "calories": 450,
        "protein": 35.5,
        "carbs": 40.0,
        "fat": 12.5
    }
            text = response.text.replace("```json", "").replace("```", "").strip()
        return eval(text)
        
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type='image/jpeg',
                ),
                prompt
            ]
        )
        text = response.text.replace("
```json", "").replace("```", "").strip()
        return eval(text)
    except Exception as e:
        st.error(f"Fehler bei der KI-Analyse: {e}")
        return None

# --- 3. STREAMLIT APPLIKATION ---
st.set_page_config(page_title="AI Nutrition Tracker", page_icon="🥗", layout="centered")

st.title("🥗 Mein KI-Ernährungstracker")

tab1, tab2 = st.tabs(["📸 Neues Essen erfassen", "📊 Historie & Rückblick"])

with tab1:
    st.header("Mahlzeit scannen")
    meal_type = st.selectbox("Kategorie", ["Frühstück", "Mittagessen", "Abendessen", "Snack/Shake"])
    
    img_file = st.file_uploader("Mach ein Foto oder lade eins hoch", type=["jpg", "jpeg", "png"])
    
    if img_file is not None:
        st.image(img_file, caption="Dein Essen", use_container_width=True)
        img_bytes = img_file.read()
        
        if st.button("🔥 Essen analysieren & speichern"):
            with st.spinner("Gemini analysiert deinen Teller..."):
                result = analyze_food_image(img_bytes)
                
                if result:
                    st.success("Erfolgreich analysiert!")
                    st.subheader(result['description'])
                    
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Kalorien", f"{result['calories']} kcal")
                    col2.metric("Proteine", f"{result['protein']}g")
                    col3.metric("Carbs", f"{result['carbs']}g")
                    col4.metric("Fett", f"{result['fat']}g")
                    
                    save_meal(meal_type, result['description'], result['calories'], result['protein'], result['carbs'], result['fat'])
                    st.toast("Mahlzeit gespeichert!", icon="💾")

with tab2:
    st.header("Dein Rückblick")
    df = get_history()
    
    if df.empty:
        st.info("Du hast bisher noch keine Mahlzeiten eingetragen.")
    else:
        today_str = datetime.now().strftime("%Y-%m-%d")
        df_today = df[df['date'] == today_str]
        
        st.subheader("Heute bereits konsumiert:")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Gesamt Kalorien", f"{int(df_today['calories'].sum())} kcal")
        c2.metric("Protein", f"{round(df_today['protein'].sum(), 1)}g")
        c3.metric("Carbs", f"{round(df_today['carbs'].sum(), 1)}g")
        c4.metric("Fett", f"{round(df_today['fat'].sum(), 1)}g")
        
        st.markdown("---")
        st.subheader("Alle gespeicherten Mahlzeiten")
        st.dataframe(
            df[['date', 'meal_type', 'description', 'calories', 'protein', 'carbs', 'fat']],
            column_config={
                "date": "Datum", "meal_type": "Typ", "description": "Was gab es?",
                "calories": "Kcal", "protein": "Eiweiß (g)", "carbs": "Kohlenhydrate (g)", "fat": "Fett (g)"
            },
            hide_index=True, use_container_width=True
        )
