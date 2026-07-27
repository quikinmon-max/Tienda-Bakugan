import streamlit as st
import pymongo
import base64
from datetime import datetime, timedelta

# ---------------- CONFIGURACIÓN DE PÁGINA ----------------
st.set_page_config(
    page_title="Bakugan Market", 
    page_icon="https://cdn-icons-png.flaticon.com/512/785/785116.png", 
    layout="wide"
)

# ---------------- IMAGEN DE FONDO HD Y ESTILOS ----------------
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
.stApp > header {{
    background-color: transparent;
}}
.block-container {{
    background-color: rgba(14, 17, 23, 0.85); 
    padding: 2rem;
    border-radius: 15px;
}}
.tarjeta-cliente {{
    background-color: rgba(255, 255, 255, 0.1);
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 10px;
    border: 1px solid #444;
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
        col_productos.update_one({"_id": doc["producto_id"]}, {"$inc": {"stock": 1}})
        col_apartados.delete_one({"_id": doc["_id"]})

limpiar_apartados_vencidos()

# =====================================================================
# =========================== MENÚ LATERAL ============================
# =====================================================================
st.sidebar.image("https://logodix.com/logo/2012028.png", width=150)
st.sidebar.header("Filtros")

tipo_busqueda = st.sidebar.selectbox("¿Qué buscas?", ["Bakugans 🔥", "Cartas 🃏"])

# Filtro dinámico: Cambia dependiendo de lo que busques
if tipo_busqueda == "Bakugans 🔥":
    categorias = ["Todos", "Pyrus 🔥", "Aquos 💧", "Ventus 🍃", "Darkus 🌑", "Haos ✨", "Subterra 🪨"]
    sub_filtro = st.sidebar.selectbox("Filtra por Atributo", categorias)
else:
    materiales = ["Todas", "Metálica", "Cartón"]
    sub_filtro = st.sidebar.selectbox("Filtra por Material", materiales)

st.sidebar.markdown("---")
admin_input = st.sidebar.text_input("🔑 Acceso Admin", type="password")

vista_admin = "Catálogo" # Vista por defecto

if admin_input == st.secrets["ADMIN_PASS"]:
    st.sidebar.success("¡Bienvenido, jefe!")
    vista_admin = st.sidebar.radio("Opciones de Administrador", ["Ver Catálogo", "➕ Agregar Producto", "📋 Ver Apartados"])
elif admin_input != "":
    st.sidebar.error("Contraseña incorrecta.")

# =====================================================================
# ======================== PANTALLA PRINCIPAL =========================
# =====================================================================

if vista_admin == "➕ Agregar Producto":
    st.title("🛠️ Agregar nuevo producto al Catálogo")
    st.markdown("---")
    
    with st.form("form_nuevo_producto", clear_on_submit=True):
        tipo_prod = st.radio("Tipo de Producto", ["Bakugan", "Carta"])
        nombre = st.text_input("Nombre / Descripción del Producto")
        
        col1, col2 = st.columns(2)
        with col1:
            # MAGIA AQUÍ: Se desactiva si seleccionas Carta
            atributo_form = st.selectbox(
                "Atributo (Solo si es Bakugan)", 
                categorias[1:], 
                disabled=(tipo_prod == "Carta")
            ) 
        with col2:
            # MAGIA AQUÍ: Se desactiva si seleccionas Bakugan
            material_form = st.selectbox(
                "Material (Solo si es Carta)", 
                materiales[1:], 
                disabled=(tipo_prod == "Bakugan")
            )
        
        precio = st.number_input("Precio ($)", min_value=0.0, step=10.0)
        stock = st.number_input("Cantidad disponible", min_value=1, step=1)
        imagen_subida = st.file_uploader("Sube la foto", type=["png", "jpg", "jpeg"])
        
        if st.form_submit_button("Subir Producto"):
            if nombre and imagen_subida and precio > 0:
                bytes_data = imagen_subida.getvalue()
                base64_str = base64.b64encode(bytes_data).decode("utf-8")
                
                nuevo_prod = {
                    "tipo": tipo_prod,
                    "nombre": nombre,
                    "precio": precio,
                    "stock": stock,
                    "imagen_b64": base64_str
                }
                
                if tipo_prod == "Bakugan":
                    nuevo_prod["atributo"] = atributo_form
                else:
                    nuevo_prod["material"] = material_form
                    
                col_productos.insert_one(nuevo_prod)
                st.success(f"¡{nombre} subido con éxito!")
            else:
                st.error("Falta el nombre, la imagen o el precio.")

elif vista_admin == "📋 Ver Apartados":
    st.title("📋 Registro de Clientes y Apartados")
    st.markdown("Aquí verás qué piezas tiene apartadas cada persona y cuánto te deben en total.")
    st.markdown("---")
    
    todos_los_apartados = list(col_apartados.find({}))
    
    if not todos_los_apartados:
        st.info("No hay apartados activos en este momento.")
    else:
        clientes_dict = {}
        for ap in todos_los_apartados:
            tel = ap.get("comprador_telefono", "Sin número")
            if tel not in clientes_dict:
                clientes_dict[tel] = []
            clientes_dict[tel].append(ap)
        
        for tel, items in clientes_dict.items():
            nombre_cliente = items[0].get("comprador_nombre", "Desconocido")
            
            st.markdown(f'<div class="tarjeta-cliente">', unsafe_allow_html=True)
            st.markdown(f"#### 👤 {nombre_cliente} | 📞 WA: {tel}")
            
            total_cliente = 0
            for item in items:
                fecha_str = item["fecha_apartado"].strftime("%d/%m %H:%M")
                precio_item = item.get("precio", 0.0)
                total_cliente += precio_item
                
                st.write(f"- **{item['nombre_producto']}** (${precio_item}) _[Apartado: {fecha_str}]_")
            
            st.markdown(f"**Total acumulado:** <span style='color:#2ecc71; font-size:1.2em;'>${total_cliente}</span>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

else:
    # --- VISTA DEL CATÁLOGO PÚBLICO ---
    st.title("🔥 Catálogo Libre")
    st.markdown("Selecciona tus piezas. **OJO:** Tienes 3 días para concretar o se pierden los apartados.")
    st.markdown("---")

    # Armamos la consulta a la base de datos dependiendo de los filtros
    if tipo_busqueda == "Bakugans 🔥":
        query = {"stock": {"$gt": 0}, "$or": [{"tipo": "Bakugan"}, {"tipo": {"$exists": False}}]}
        if sub_filtro != "Todos":
            query["atributo"] = sub_filtro
    else:
        query = {"stock": {"$gt": 0}, "tipo": "Carta"}
        if sub_filtro != "Todas":
            query["material"] = sub_filtro

    productos = list(col_productos.find(query))

    if not productos:
        st.info("No hay inventario disponible con estos filtros por el momento.")
    else:
        cols = st.columns(3)
        for index, prod in enumerate(productos):
            col = cols[index % 3] 
            with col:
                st.markdown(f"### {prod['nombre']}")
                if "imagen_b64" in prod:
                    st.image(base64.b64decode(prod["imagen_b64"]), use_container_width=True)
                
                precio_mostrar = prod.get('precio', 0.0)
                
                # Mostramos si es atributo (Bakugan) o material (Carta)
                if tipo_busqueda == "Bakugans 🔥":
                    st.write(f"**Atributo:** {prod.get('atributo', 'N/A')}")
                else:
                    st.write(f"**Material:** {prod.get('material', 'N/A')}")
                    
                st.write(f"**Disponibles:** {prod['stock']}")
                st.write(f"**Precio:** ${precio_mostrar}")
                
                with st.expander("🛒 Apartar pieza"):
                    if st.session_state.get(f"apartado_{prod['_id']}", False):
                        st.success("✅ ¡Tu apartado está asegurado!")
                        # CAMBIA ESTE NÚMERO POR TU CELULAR
                        link_wa = f"https://wa.me/521234567890?text=Hola,%20acabo%20de%20apartar%20{prod['nombre']}%20por%20${precio_mostrar}"
                        st.markdown(f"[**📲 HAZ CLIC AQUÍ PARA ENVIARME WHATSAPP**]({link_wa})")
                    else:
                        st.write(f"**Total a pagar:** ${precio_mostrar}")
                        st.caption("🚨 *Nota: El costo de envío es aparte.*")
                        
                        nom = st.text_input("Tu Nombre", key=f"n_{prod['_id']}")
                        tel = st.text_input("Tu WhatsApp", key=f"t_{prod['_id']}")
                        
                        if st.button("Confirmar Apartado", key=f"btn_{prod['_id']}"):
                            if nom and tel:
                                col_apartados.insert_one({
                                    "producto_id": prod["_id"],
                                    "nombre_producto": prod["nombre"],
                                    "precio": precio_mostrar,
                                    "comprador_nombre": nom,
                                    "comprador_telefono": tel,
                                    "fecha_apartado": datetime.now()
                                })
                                col_productos.update_one({"_id": prod["_id"]}, {"$inc": {"stock": -1}})
                                st.session_state[f"apartado_{prod['_id']}"] = True
                                st.rerun() 
                            else:
                                st.warning("Escribe tu nombre y teléfono para apartarlo.")