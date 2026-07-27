import streamlit as st
import pymongo
import base64
from datetime import datetime, timedelta

# ---------------- CONFIGURACIÓN DE PÁGINA ----------------
# Aquí cambias la URL por la de tu propio ícono (favicon)
st.set_page_config(
    page_title="Bakugan Market", 
    page_icon="https://cdn-icons-png.flaticon.com/512/785/785116.png", 
    layout="wide"
)

# ---------------- IMAGEN DE FONDO HD Y ESTILOS ----------------
# Reemplaza el enlace con la URL de tu imagen en alta resolución
imagen_de_fondo = "https://images.hdqwalls.com/download/bakugan-battle-brawlers-2v-1920x1080.jpg"

fondo_css = f"""
<style>
.stApp {{
    background-image: url("{imagen_de_fondo}");
    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;
    background-attachment: fixed;
}}
/* Esto le pone un fondo semi-transparente oscuro al contenido principal */
.stApp > header {{
    background-color: transparent;
}}
.block-container {{
    background-color: rgba(14, 17, 23, 0.85); /* 85% de opacidad para que se lea el texto */
    padding: 2rem;
    border-radius: 15px;
}}
</style>
"""
st.markdown(fondo_css, unsafe_allow_html=True)

# ---------------- CONEXIÓN A MONGODB ----------------
@st.cache_resource
def init_connection():
    MONGO_URI = st.secrets["MONGO_URI"] 
    client = pymongo.MongoClient(MONGO_URI)
    return client

client = init_connection()
db = client["bakugan_market"]
col_productos = db["productos"]
col_apartados = db["apartados"]

# ---------------- LÓGICA DE CADUCIDAD (3 DÍAS) ----------------
def limpiar_apartados_vencidos():
    limite_fecha = datetime.now() - timedelta(days=3)
    
    vencidos = col_apartados.find({"fecha_apartado": {"$lt": limite_fecha}})
    
    for doc in vencidos:
        col_productos.update_one(
            {"_id": doc["producto_id"]}, 
            {"$inc": {"stock": 1}}
        )
        col_apartados.delete_one({"_id": doc["_id"]})

limpiar_apartados_vencidos()

# ---------------- MENÚ LATERAL (CATEGORÍAS Y ADMIN) ----------------
# Imagen corregida del menú lateral
st.sidebar.image("https://logodix.com/logo/2012028.png", width=150)
st.sidebar.header("Filtros")

categorias = ["Todos", "Pyrus 🔥", "Aquos 💧", "Ventus 🍃", "Darkus 🌑", "Haos ✨", "Subterra 🪨"]
categoria_seleccionada = st.sidebar.selectbox("Filtra por Atributo", categorias)

# --- PANEL DE ADMINISTRADOR ---
st.sidebar.markdown("---")
if st.sidebar.checkbox("🔒 Modo Admin (Editar Catálogo)"):
    st.sidebar.success("Modo edición activado")
    st.subheader("🛠️ Agregar nuevo Bakugan")
    
    with st.form("form_nuevo_bakugan", clear_on_submit=True):
        nombre = st.text_input("Nombre del Bakugan (ej. Dragonoid)")
        atributo = st.selectbox("Atributo", categorias[1:]) 
        stock = st.number_input("Cantidad disponible", min_value=1, step=1)
        imagen_subida = st.file_uploader("Sube la foto", type=["png", "jpg", "jpeg"])
        
        btn_guardar = st.form_submit_button("Subir al Catálogo")
        
        if btn_guardar:
            if nombre and imagen_subida:
                bytes_data = imagen_subida.getvalue()
                base64_str = base64.b64encode(bytes_data).decode("utf-8")
                
                nuevo_bakugan = {
                    "nombre": nombre,
                    "atributo": atributo,
                    "stock": stock,
                    "imagen_b64": base64_str
                }
                col_productos.insert_one(nuevo_bakugan)
                st.success(f"¡{nombre} agregado exitosamente!")
                st.rerun() 
            else:
                st.error("Falta el nombre o la imagen.")

# ---------------- CATÁLOGO PÚBLICO ----------------
st.title("🔥 Catálogo Bakugan Libre")
st.markdown("Selecciona tus piezas. **OJO:** Tienes 3 días para concretar o se pierden los apartados.")
st.markdown("---")

query = {"stock": {"$gt": 0}} 
if categoria_seleccionada != "Todos":
    query["atributo"] = categoria_seleccionada

bakugans = list(col_productos.find(query))

if not bakugans:
    st.info("No hay Bakugans disponibles en esta categoría por el momento.")
else:
    cols = st.columns(3)
    
    for index, bkg in enumerate(bakugans):
        col = cols[index % 3] 
        
        with col:
            st.markdown(f"### {bkg['nombre']}")
            
            if "imagen_b64" in bkg:
                imagen_bytes = base64.b64decode(bkg["imagen_b64"])
                st.image(imagen_bytes, use_container_width=True)
            
            st.write(f"**Atributo:** {bkg['atributo']}")
            st.write(f"**Disponibles:** {bkg['stock']}")
            
            with st.expander("Apartar pieza"):
                contacto = st.text_input("Tu Nombre/WhatsApp", key=f"contacto_{bkg['_id']}")
                if st.button("Confirmar Apartado", key=f"btn_{bkg['_id']}"):
                    if contacto:
                        nuevo_apartado = {
                            "producto_id": bkg["_id"],
                            "nombre_producto": bkg["nombre"],
                            "comprador": contacto,
                            "fecha_apartado": datetime.now()
                        }
                        col_apartados.insert_one(nuevo_apartado)
                        
                        col_productos.update_one(
                            {"_id": bkg["_id"]},
                            {"$inc": {"stock": -1}}
                        )
                        
                        st.success(f"¡Apartado a nombre de {contacto}!")
                        st.rerun() 
                    else:
                        st.warning("Escribe tu nombre o contacto para apartarlo.")