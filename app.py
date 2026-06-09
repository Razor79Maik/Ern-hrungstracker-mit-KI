import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
from google import genai
from google.genai import types
import json

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

def delete_all_history():
    conn = sqlite3.connect("nutrition_tracker.db")
    c = conn.cursor()
    c.execute("DELETE FROM meals")
    conn.commit()
    conn.close()

def delete_last_entry():
    conn = sqlite3.connect("nutrition_tracker.db")
    c = conn.cursor()
    c.execute("DELETE FROM meals WHERE id = (SELECT MAX(id) FROM meals)")
    conn.commit()
    conn.close()

# --- 2. GEMINI API SETUP ---
api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

def analyze_food_image(image_bytes):
    prompt = """
    Analysiere dieses Bild von Essen. Schätze die einzelnen Zutaten mit Gramm-Angaben, Portionsgrößen und berechne die Nährwerte.
    Antworte AUSSCHLIESSLICH im folgenden JSON-Format ohne Markdown (keine ```json Blöcke):
    {
        "description": "Kurze Zusammenfassung (z.B. Körnerbrötchen mit Lachs)",
        "ingredients": "z.B. 80g Körnerbrötchen, 60g Räucherlachs, 5g Dill, 10g Butter",
        "calories": 450,
        "protein": 35.5,
        "carbs": 40.0,
        "fat": 12.5
    }
    Achte auf eine realistische Schätzung für einen Sportler.
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                prompt
            ]
        )
        text = response.text.strip()
        if "
```" in text:
            text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        st.error(f"Fehler bei der KI-Analyse: {e}")
        return None

# NEU: Funktion für die manuelle Text-Abfrage der Nährwerte
def fetch_manual_macros(food_text):
    prompt = f"""
    Berechne oder schätze die Nährwerte für folgende Eingabe: "{food_text}". 
    Berücksichtige dabei unbedingt die genannte Mengenangabe (z.B. Gramm). Wenn keine Menge genannt wird, nimm eine Standardportion an.
    Antworte AUSSCHLIESSLICH im folgenden JSON-Format ohne Markdown (keine ```json Blöcke):
    {{
        "calories": 350,
        "protein": 25.0,
        "carbs": 40.0,
        "fat": 5.0
    }}
    Achte auf hohe Genauigkeit für Sportler-Lebensmittel.
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        text = response.text.strip()
        if "
```" in text:
            text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        st.error(f"Fehler beim Abrufen der Nährwerte: {e}")
        return None

# --- 3. STREAMLIT APPLIKATION ---
st.set_page_config(page_title="AI Nutrition Tracker", page_icon="🥗", layout="centered")
st.title("🥗 Mein KI-Ernährungstracker")

# Session States initialisieren, damit die Werte bei manueller Eingabe erhalten bleiben
if 'manual_cal' not in st.session_state: st.session_state['manual_cal'] = 0
if 'manual_pro' not in st.session_state: st.session_state['manual_pro'] = 0.0
if 'manual_carb' not in st.session_state: st.session_state['manual_carb'] = 0.0
if 'manual_fat' not in st.session_state: st.session_state['manual_fat'] = 0.0

tab1, tab2 = st.tabs(["📥 Essen eintragen", "📊 Historie & Rückblick"])

with tab1:
    st.header("Mahlzeit erfassen")
    meal_type = st.selectbox("Kategorie", ["Frühstück", "Mittagessen", "Abendessen", "Snack/Shake"])
    
    input_method = st.radio("Methode wählen:", ["📸 Foto scannen", "✍️ Manuell eingeben"], horizontal=True)
    
    if input_method == "📸 Foto scannen":
        img_file = st.file_uploader("Mach ein Foto oder lade eins hoch", type=["jpg", "jpeg", "png"])
        
        if img_file is not None:
            st.image(img_file, caption="Dein Essen", use_container_width=True)
            img_bytes = img_file.read()
            
            if st.button("🔍 Foto von KI analysieren lassen"):
                with st.spinner("Gemini analysiert deinen Teller und schätzt die Zutaten..."):
                    result = analyze_food_image(img_bytes)
                    if result:
                        st.session_state['ki_result'] = result
                        st.success("Analyse fertig! Du kannst die Werte unten jetzt prüfen und anpassen.")

            if 'ki_result' in st.session_state:
                res = st.session_state['ki_result']
                st.markdown("---")
                st.subheader("📋 KI-Vorschlag (Hier anpassen):")
                
                edit_desc = st.text_input("Gericht Name / Beschreibung", value=res.get('description', ''))
                edit_ing = st.text_area("Zutaten & Gramm-Angaben", value=res.get('ingredients', ''))
                
                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    edit_cal = st.number_input("Kalorien (kcal)", min_value=0, value=int(res.get('calories', 0)), step=1)
                    edit_pro = st.number_input("Eiweiß (g)", min_value=0.0, value=float(res.get('protein', 0)), step=0.1)
                with col_e2:
                    edit_carb = st.number_input("Kohlenhydrate (g)", min_value=0.0, value=float(res.get('carbs', 0)), step=0.1)
                    edit_fat = st.number_input("Fett (g)", min_value=0.0, value=float(res.get('fat', 0)), step=0.1)
                
                if st.button("💾 Bestätigen & in Historie speichern"):
                    full_description = f"{edit_desc} ({edit_ing})" if edit_ing else edit_desc
                    save_meal(meal_type, full_description, int(edit_cal), round(edit_pro, 1), round(edit_carb, 1), round(edit_fat, 1))
                    st.success("Mahlzeit erfolgreich gespeichert!")
                    st.toast("Gespeichert!", icon="💾")
                    del st.session_state['ki_result']
                    st.rerun()
                        
    else:  # ✍️ Manuell eingeben
        st.subheader("Manuelle Werte eingeben")
        
        # Eingabefeld für das Lebensmittel + Menge
        manual_desc = st.text_input(
            "Was hast du gegessen? (Bitte mit Menge)", 
            placeholder="z.B. 150g Putenhack, 60g Haferkleie, 250g Magerquark..."
        )
        
        # NEU: Button, um die Nährwerte sofort via KI abzurufen
        if st.button("✨ Nährwerte automatisch berechnen"):
            if manual_desc:
                with st.spinner("Berechne Nährwerte..."):
                    macros = fetch_manual_macros(manual_desc)
                    if macros:
                        st.session_state['manual_cal'] = int(macros.get('calories', 0))
                        st.session_state['manual_pro'] = float(macros.get('protein', 0.0))
                        st.session_state['manual_carb'] = float(macros.get('carbs', 0.0))
                        st.session_state['manual_fat'] = float(macros.get('fat', 0.0))
                        st.success("Werte erfolgreich berechnet! Du kannst sie unten noch anpassen.")
            else:
                st.warning("Bitte gib zuerst ein Lebensmittel und eine Menge ein!")
        
        # Die Zahlenfelder spiegeln den Session State wider und erlauben manuelle Korrekturen
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            manual_cal = st.number_input("Kalorien (kcal)", min_value=0, value=st.session_state['manual_cal'], step=1)
            manual_pro = st.number_input("Eiweiß (g)", min_value=0.0, value=st.session_state['manual_pro'], step=0.1)
        with col_m2:
            manual_carb = st.number_input("Kohlenhydrate (g)", min_value=0.0, value=st.session_state['manual_carb'], step=0.1)
            manual_fat = st.number_input("Fett (g)", min_value=0.0, value=st.session_state['manual_fat'], step=0.1)
            
        if st.button("💾 Manuelle Mahlzeit speichern"):
            if not manual_desc:
                st.warning("Bitte gib eine kurze Beschreibung ein!")
            else:
                save_meal(meal_type, manual_desc, int(manual_cal), round(manual_pro, 1), round(manual_carb, 1), round(manual_fat, 1))
                st.success(f"'{manual_desc}' wurde erfolgreich gespeichert!")
                st.toast("Mahlzeit gespeichert!", icon="💾")
                # Nach dem Speichern die Werte im Speicher wieder zurücksetzen
                st.session_state['manual_cal'] = 0
                st.session_state['manual_pro'] = 0.0
                st.session_state['manual_carb'] = 0.0
                st.session_state['manual_fat'] = 0.0
                st.rerun()

with tab2:
    st.header("Dein Rückblick")
    df = get_history()
    
    if df.empty:
        st.info("Du hast bisher noch keine Mahlzeiten eingetragen.")
    else:
        st.subheader("📅 Tag auswählen")
        selected_date = st.date_input("Welchen Tag möchtest du sehen?", value=date.today())
        selected_date_str = selected_date.strftime("%Y-%m-%d")
        
        df_selected = df[df['date'] == selected_date_str]
        
        st.markdown(f"### Konsumiert am {selected_date.strftime('%d.%m.%Y')}:")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Gesamt Kalorien", f"{int(df_selected['calories'].sum())} kcal")
        c2.metric("Protein", f"{round(df_selected['protein'].sum(), 1)}g")
        c3.metric("Carbs", f"{round(df_selected['carbs'].sum(), 1)}g")
        c4.metric("Fett", f"{round(df_selected['fat'].sum(), 1)}g")
        
        st.markdown("---")
        st.subheader("Mahlzeiten an diesem Tag")
        
        if df_selected.empty:
            st.info("An diesem Tag wurden keine Mahlzeiten eingetragen.")
        else:
            st.dataframe(
                df_selected[['meal_type', 'description', 'calories', 'protein', 'carbs', 'fat']],
                column_config={
                    "meal_type": "Typ", "description": "Was gab es? (Zutaten)",
                    "calories": "Kcal", "protein": "Eiweiß (g)", "carbs": "Kohlenhydrate (g)", "fat": "Fett (g)"
                },
                hide_index=True, use_container_width=True
            )
        
        st.markdown("---")
        st.subheader("⚙️ Daten verwalten")
        
        col_del1, col_del2 = st.columns(2)
        with col_del1:
            if st.button("🗑️ Letzten Eintrag löschen"):
                delete_last_entry()
                st.success("Der letzte Eintrag wurde gelöscht!")
                st.rerun()
                
        with col_del2:
            if st.checkbox("Ich möchte wirklich ALLE Daten löschen"):
                if st.button("🚨 Komplette Historie löschen"):
                    delete_all_history()
                    st.success("Alle Daten wurden erfolgreich gelöscht!")
                    st.rerun()
