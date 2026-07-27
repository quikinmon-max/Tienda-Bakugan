import streamlit as st
import pymongo
import base64
from datetime import datetime, timedelta
from bson.objectid import ObjectId

# ---------------- CONFIGURACIÓN DE PÁGINA ----------------
st.set_page_config(page_title="Bakugan Market", page_icon="🔥", layout="wide")

# ---------------- CONEXIÓN A MONGODB (SEGURO PARA GITHUB) ----------------
# Se usa st.cache_resource para no abrir múltiples conexiones
@st.cache_resource
def init_connection():
    # En lugar de tener el texto aquí, Streamlit jalará la conexión de forma segura
    # desde la configuración de "Secrets" en la nube
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
    
    # Buscar apartados más antiguos que 3 días
    vencidos = col_apartados.find({"fecha_apartado": {"$lt": limite_fecha}})
    
    for doc in vencidos:
        # Regresamos 1 de stock al producto
        col_productos.update_one(
            {"_id": doc["producto_id"]}, 
            {"$inc": {"stock": 1}}
        )
        # Eliminamos el registro del apartado
        col_apartados.delete_one({"_id": doc["_id"]})

# Ejecutamos la limpieza silenciosamente cada vez que alguien entra
limpiar_apartados_vencidos()

# ---------------- MENÚ LATERAL (CATEGORÍAS Y ADMIN) ----------------
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/Bakugan_logo.svg/512px-Bakugan_logo.svg.png", width=150)
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
        atributo = st.selectbox("Atributo", categorias[1:]) # Quitamos "Todos" de las opciones
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
                st.rerun() # Recarga la app para mostrar el nuevo producto
            else:
                st.error("Falta el nombre o la imagen.")

# ---------------- CATÁLOGO PÚBLICO ----------------
st.title("🔥 Catálogo Bakugan Libre")
st.markdown("Selecciona tus piezas. **OJO:** Tienes 3 días para concretar o se pierden los apartados.")
st.markdown("---")

# Construir la consulta a Mongo según el filtro
query = {"stock": {"$gt": 0}} # Solo mostrar los que tienen stock
if categoria_seleccionada != "Todos":
    query["atributo"] = categoria_seleccionada

bakugans = list(col_productos.find(query))

if not bakugans:
    st.info("No hay Bakugans disponibles en esta categoría por el momento.")
else:
    # Mostrar productos en formato de cuadrícula (3 columnas)
    cols = st.columns(3)
    
    for index, bkg in enumerate(bakugans):
        col = cols[index % 3] # Distribuye los items en las 3 columnas
        
        with col:
            st.markdown(f"### {bkg['nombre']}")
            
            # Decodificar y mostrar imagen
            if "imagen_b64" in bkg:
                imagen_bytes = base64.b64decode(bkg["imagen_b64"])
                st.image(imagen_bytes, use_container_width=True)
            
            st.write(f"**Atributo:** {bkg['atributo']}")
            st.write(f"**Disponibles:** {bkg['stock']}")
            
            # Pequeño formulario para apartar
            with st.expander("Apartar pieza"):
                contacto = st.text_input("Tu Nombre/WhatsApp", key=f"contacto_{bkg['_id']}")
                if st.button("Confirmar Apartado", key=f"btn_{bkg['_id']}"):
                    if contacto:
                        # 1. Registrar el apartado con fecha actual
                        nuevo_apartado = {
                            "producto_id": bkg["_id"],
                            "nombre_producto": bkg["nombre"],
                            "comprador": contacto,
                            "fecha_apartado": datetime.now()
                        }
                        col_apartados.insert_one(nuevo_apartado)
                        
                        # 2. Restar 1 al stock del producto
                        col_productos.update_one(
                            {"_id": bkg["_id"]},
                            {"$inc": {"stock": -1}}
                        )
                        
                        st.success(f"¡Apartado a nombre de {contacto}!")
                        st.rerun() # Refresca la interfaz para actualizar el stock visible
                    else:
                        st.warning("Escribe tu nombre o contacto para apartarlo.")