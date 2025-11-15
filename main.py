# bot_zonas.py
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)
from pytz import timezone
from datetime import datetime, timedelta
from logging import basicConfig, getLogger, INFO, WARNING

# Constants
TOKEN = "8150577858:AAFp74F_ubS1nwAz39U2CLDBplnsXxb2yK8"
CREATOR_USERNAME = "@Soy_MrNick"
ROTATION_DURATION_MINUTES = 120
DICE_NAME = "PRADA"

# Setup logging
basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=INFO)
logger = getLogger(__name__)
getLogger("httpx").setLevel(WARNING)
getLogger("httpcore").setLevel(WARNING)

# In-memory data
zones = {"z1": None, "z2": None}
waiting_list = []
authorized = False
list_open = False
last_rotation_time = None
rotation_job = None
authorized_chat_id = None

# Time zones
timezones = {
    "🇨🇴 Hora Colombia 🇨🇴": "America/Bogota",
    "🇲🇽 Hora México 🇲🇽": "America/Mexico_City",
    "🇻🇪 Hora Venezuela 🇻🇪": "America/Caracas",
    "🇦🇷 Hora Argentina / Chile 🇨🇱": "America/Argentina/Buenos_Aires",
    "🇪🇸 Hora España 🇪🇸": "Europe/Madrid",
}

# Helper
def get_time_display():
    now = datetime.now()
    start = last_rotation_time if last_rotation_time else now
    end = start + timedelta(minutes=ROTATION_DURATION_MINUTES)

    lines = []
    for country, tz in timezones.items():
        t_start = start.astimezone(timezone(tz)).strftime("%H:%M")
        t_end = end.astimezone(timezone(tz)).strftime("%H:%M")
        lines.append(f"{country} \n⏰ {t_start} ➖ {t_end}")
    return "\n".join(lines)

def is_creator(user):
    return user.username == CREATOR_USERNAME[1:]

async def is_admin(context, chat_id, user_id):
    member = await context.bot.get_chat_member(chat_id, user_id)
    return member.status in ["administrator", "creator"]

def format_list():
    zona_display = "\n\n🏷️ Zonas Actuales:\n"
    for z, u in zones.items():
        zona_display += f"🔹 Zona {z[1]}⃣: {u if u else '⚪ Vacío'}\n"

    formatted_waiting_list = []
    for i, item in enumerate(waiting_list, 1):
        formatted_waiting_list.append(f"🔸 {item}")
        if i % 2 == 0 and i < len(waiting_list):
            formatted_waiting_list.append("")

    espera = "\n".join(formatted_waiting_list) if waiting_list else "🔘 Ninguno"

    mins_left = (
        ROTATION_DURATION_MINUTES
        - int((datetime.now() - last_rotation_time).seconds / 60)
        if last_rotation_time else 0
    )
    mins_left = max(mins_left, 0)

    return (
        f"⚜️ Lista de Zonas {DICE_NAME} ⚜️\n\n"
        f"⏰ Horarios de Rotación:\n{get_time_display()}"
        f"{zona_display}"
        f"\n⏳ Próxima rotación en: {mins_left} minutos\n"
        f"\n📋 Lista de Espera:\n{espera}"
    )

async def validate_message(update: Update):
    if not update.message:
        return False
    return True

async def reject_private_messages(update: Update):
    if not await validate_message(update):
        return False
    if update.effective_chat.type == "private":
        await update.message.reply_text("🚫 Este bot no funciona por mensajes privados.")
        return False
    return True

async def check_authorized_chat(update: Update):
    if not await validate_message(update):
        return False

    current_chat_id = update.effective_chat.id

    if not authorized or authorized_chat_id is None:
        await update.message.reply_text("🚫 Este bot no está autorizado actualmente.")
        return False

    if current_chat_id != authorized_chat_id:
        await update.message.reply_text("🚫 Este bot solo funciona en el grupo autorizado.")
        return False

    return True

# -------------------------
#  COMANDOS
# -------------------------

async def cmd_autorizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global authorized, authorized_chat_id, waiting_list, zones

    if not await reject_private_messages(update):
        return

    user = update.effective_user
    chat_id = update.effective_chat.id

    if is_creator(user):
        authorized = True
        authorized_chat_id = chat_id

        # Reset
        zones = {"z1": None, "z2": None}
        waiting_list.clear()

        setup_rotation_job(context, chat_id)

        await update.message.reply_text(
            f"🔓 Bot autorizado para este grupo.\n🆔 Chat ID: `{chat_id}`"
        )
    else:
        await update.message.reply_text("🚫 Solo el creador puede autorizar el bot.")

def setup_rotation_job(context, chat_id):
    global rotation_job
    if rotation_job:
        rotation_job.schedule_removal()

    rotation_job = context.job_queue.run_repeating(
        job_rotacion,
        interval=ROTATION_DURATION_MINUTES * 60,
        first=ROTATION_DURATION_MINUTES * 60,
        data=chat_id,
    )

async def cmd_desautorizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global authorized, authorized_chat_id, list_open, rotation_job, zones, waiting_list

    if not await reject_private_messages(update):
        return

    if not is_creator(update.effective_user):
        await update.message.reply_text("🚫 Solo el creador puede desautorizar.")
        return

    authorized = False
    authorized_chat_id = None
    list_open = False
    zones = {"z1": None, "z2": None}
    waiting_list = []

    if rotation_job:
        rotation_job.schedule_removal()
        rotation_job = None

    await update.message.reply_text("🔒 Bot desactivado correctamente.")

async def check_authorized(update):
    return await check_authorized_chat(update)

async def check_list_open(update):
    if not await validate_message(update):
        return False
    if not list_open:
        await update.message.reply_text("🚫 La lista está cerrada actualmente.")
        return False
    return True

async def cmd_lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await reject_private_messages(update): return
    if not await check_authorized(update): return
    if not await check_list_open(update): return
    await update.message.reply_text(format_list())

# -------------------------
# REEMPLAZO DE LAMBDAS
# -------------------------

async def cmd_z1(update, context):
    await assign_zone(update, "z1", context)

async def cmd_z2(update, context):
    await assign_zone(update, "z2", context)

async def cmd_exitz1(update, context):
    await remove_zone(update, "z1")

async def cmd_exitz2(update, context):
    await remove_zone(update, "z2")

# -------------------------

async def assign_zone(update, zone, context: ContextTypes.DEFAULT_TYPE):
    if not await reject_private_messages(update): return
    if not await check_authorized(update): return
    if not await check_list_open(update): return

    username = context.args[0] if context.args else f"@{update.effective_user.username}"

    # Verificaciones
    for current_zone, occupant in zones.items():
        if occupant == username:
            await update.message.reply_text(
                f"⚠️ Ya estás en la zona {current_zone[1]}⃣."
            )
            return

    if username in waiting_list:
        await update.message.reply_text("⚠️ Estás en la lista de espera.")
        return

    if zones[zone] is None:
        zones[zone] = username
        await update.message.reply_text(f"✅ {username} asignado a Zona {zone[1]}⃣")
    else:
        await update.message.reply_text(f"⚠️ La zona {zone[1]}⃣ está ocupada.")

    await update.message.reply_text(format_list())

async def remove_zone(update, zone):
    if not await reject_private_messages(update): return
    if not await check_authorized(update): return
    if not await check_list_open(update): return

    username = f"@{update.effective_user.username}"

    if zones[zone] == username:
        zones[zone] = None
        await update.message.reply_text(f"🚫 {username} salió de Zona {zone[1]}⃣")
    else:
        await update.message.reply_text(f"⚠️ No estás en esa zona.")

    await update.message.reply_text(format_list())

async def cmd_espera(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await reject_private_messages(update): return
    if not await check_authorized(update): return
    if not await check_list_open(update): return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if context.args:
        if not await is_admin(context, chat_id, user_id):
            await update.message.reply_text(
                "🚫 Solo administradores pueden añadir a otros."
            )
            return
        username = context.args[0]
    else:
        username = f"@{update.effective_user.username}"

    for zone, occupant in zones.items():
        if occupant == username:
            await update.message.reply_text(
                f"⚠️ {username} ya está en una zona."
            )
            return

    if username in waiting_list:
        await update.message.reply_text("⚠️ Ya estás en la lista de espera.")
    else:
        waiting_list.append(username)
        await update.message.reply_text(f"📥 {username} añadido a la lista.")

    await update.message.reply_text(format_list())

async def cmd_cambiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await reject_private_messages(update): return
    if not await check_authorized(update): return
    if not await check_list_open(update): return

    args = context.args
    user = update.effective_user
    username1 = f"@{user.username}"

    if len(args) == 0:
        await update.message.reply_text(
            "❌ Usa /cambiar @Usuario o /cambiar @Usuario1 @Usuario2"
        )
        return

    if len(args) == 1:
        username2 = args[0]
    elif len(args) == 2:
        if not is_creator(user) and not await is_admin(
            context, update.effective_chat.id, user.id
        ):
            await update.message.reply_text(
                "🚫 Solo administradores pueden intercambiar a otros."
            )
            return
        username1, username2 = args
    else:
        await update.message.reply_text("❌ Formato incorrecto.")
        return

    if username1 == username2:
        await update.message.reply_text("❌ No puedes intercambiarte contigo mismo.")
        return

    def find_user_position(username):
        for zone, occupant in zones.items():
            if occupant == username:
                return ("zone", zone)
        if username in waiting_list:
            return ("wait", waiting_list.index(username))
        return None

    pos1 = find_user_position(username1)
    pos2 = find_user_position(username2)

    if not pos1 and not pos2:
        await update.message.reply_text("❌ Ninguno de los dos está en zonas/espera.")
        return

    # Intercambiar posiciones
    if pos1 and pos2:
        if pos1[0] == "zone" and pos2[0] == "zone":
            zones[pos1[1]], zones[pos2[1]] = zones[pos2[1]], zones[pos1[1]]
        elif pos1[0] == "zone" and pos2[0] == "wait":
            zones[pos1[1]] = username2
            waiting_list[pos2[1]] = username1
        elif pos1[0] == "wait" and pos2[0] == "zone":
            zones[pos2[1]] = username1
            waiting_list[pos1[1]] = username2
        else:
            waiting_list[pos1[1]], waiting_list[pos2[1]] = (
                waiting_list[pos2[1]],
                waiting_list[pos1[1]],
            )
    elif pos1 and not pos2:
        if pos1[0] == "zone":
            zones[pos1[1]] = username2
        else:
            waiting_list[pos1[1]] = username2
    elif pos2 and not pos1:
        if pos2[0] == "zone":
            zones[pos2[1]] = username1
        else:
            waiting_list[pos2[1]] = username1

    await update.message.reply_text(
        f"🔁 Intercambio realizado: {username1} ↔ {username2}"
    )
    await update.message.reply_text(format_list())

async def cmd_exit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await reject_private_messages(update): return
    if not await check_authorized(update): return
    if not await check_list_open(update): return

    user_requesting = update.effective_user
    args = context.args
    target_username = f"@{user_requesting.username}"

    if args:
        if args[0].startswith("@"):
            target_username = args[0]
        else:
            await update.message.reply_text("⚠️ Usa /exit @usuario")
            return

    removed = False

    for zone in zones:
        if zones[zone] == target_username:
            zones[zone] = None
            removed = True

    for i, user in enumerate(waiting_list):
        if user == target_username:
            waiting_list[i] = "Libre"
            removed = True
            break

    if removed:
        await update.message.reply_text(f"✅ {target_username} eliminado correctamente.")
    else:
        await update.message.reply_text("⚠️ No estaba en zonas ni en espera.")

    await update.message.reply_text(format_list())

async def cmd_tomarlibre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await reject_private_messages(update): return
    if not await check_authorized(update): return
    if not await check_list_open(update): return

    if not waiting_list:
        await update.message.reply_text("⚠️ No hay lugares libres.")
        return

    username = f"@{update.effective_user.username}"

    for zone, occupant in zones.items():
        if occupant == username:
            await update.message.reply_text(
                f"⚠️ Ya estás en Zona {zone[1]}⃣."
            )
            return

    if username in waiting_list:
        await update.message.reply_text(
            "⚠️ Ya estás en la lista de espera."
        )
        return

    libre_index = None
    for i, user in enumerate(waiting_list):
        if user == "Libre":
            libre_index = i
            break

    if libre_index is not None:
        waiting_list[libre_index] = username
        await update.message.reply_text(
            f"✅ {username} tomó un lugar libre."
        )
        await update.message.reply_text(format_list())
        return

    await update.message.reply_text("⚠️ No hay lugares libres disponibles.")

async def cmd_abrir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global list_open, last_rotation_time

    if not await reject_private_messages(update): return
    if not await check_authorized(update): return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if await is_admin(context, chat_id, user_id):
        if list_open:
            await update.message.reply_text("🔓 La lista ya está abierta.")
            return

        list_open = True
        last_rotation_time = datetime.now()

        if rotation_job:
            setup_rotation_job(context, authorized_chat_id)

        await update.message.reply_text("🔓 Lista abierta.")
        await update.message.reply_text(format_list())
    else:
        await update.message.reply_text("🚫 Solo administradores pueden abrir la lista.")

async def cmd_cerrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global list_open

    if not await reject_private_messages(update): return
    if not await check_authorized(update): return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if await is_admin(context, chat_id, user_id):
        if not list_open:
            await update.message.reply_text("🔒 La lista ya está cerrada.")
            return

        list_open = False
        await update.message.reply_text("🔒 Lista cerrada.")
    else:
        await update.message.reply_text("🚫 Solo administradores pueden cerrar la lista.")

async def cmd_reglas(update, context):
    if not await reject_private_messages(update): return
    if not await check_authorized(update): return

    await update.message.reply_text(
        """📜 Reglas del Sistema de Zonas:
1️⃣ Usa las zonas solo si estás disponible.
2️⃣ Respeta los turnos y rotaciones.
3️⃣ Usa /exit para salir de zona o lista.
4️⃣ No abuses del sistema.
5️⃣ No editar mensajes con comandos.

✅ ¡Convivencia primero!"""
    )

async def cmd_comandos(update, context):
    if not await check_authorized(update): return
    await update.message.reply_text(
        """📌 Menú de Comandos:

▶️ Usuarios:
/z1 /z2 - Asignarte a zona
/z1 @usuario /z2 @usuario - Asignar a otro usuario
/exitz1 /exitz2 - Salir de zona
/espera - Unirse a la lista de espera
/exit - Salir de zona o lista
/exit @usuario - Sacar a otro usuario
/cambiar @usuario - Cambiar zonas/espera
/tomarlibre - Tomar lugar libre
/lista - Ver estado actual
/reglas - Reglas
/comandos - Menú

▶️ Admin:
/abrir - Abrir lista
/cerrar - Cerrar lista

▶️ Creador:
/autorizar - Activar bot
/desautorizar - Desactivar bot

▶️ Utilidad:
/chatid - ID del chat actual"""
    )

async def job_rotacion(context):
    global zones, waiting_list, last_rotation_time

    if not list_open or not authorized_chat_id:
        return

    chat_id = context.job.data

    if chat_id != authorized_chat_id:
        return

    logger.info("🔁 Ejecutando rotación...")

    new_zones = {zone: None for zone in zones}

    for i, zone in enumerate(zones.keys()):
        if i < len(waiting_list):
            if waiting_list[i] != "Libre":
                new_zones[zone] = waiting_list[i]
            else:
                new_zones[zone] = None

    waiting_list = waiting_list[len(zones):] if len(waiting_list) > len(zones) else []
    zones = new_zones
    last_rotation_time = datetime.now()

    await context.bot.send_message(
        chat_id=chat_id,
        text="🔁 Rotación realizada automáticamente\n\n" + format_list(),
    )

async def cmd_chatid(update, context):
    if not await reject_private_messages(update): return
    if not await check_authorized(update): return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if await is_admin(context, chat_id, user_id):
        status = "✅ AUTORIZADO" if chat_id == authorized_chat_id else "❌ NO AUTORIZADO"
        await update.message.reply_text(
            f"🆔 ID de este chat: `{chat_id}`\n📊 Estado: {status}"
        )
    else:
        await update.message.reply_text("🚫 No tienes permisos.")

# -------------------------
# MAIN
# -------------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("autorizar", cmd_autorizar))
    app.add_handler(CommandHandler("desautorizar", cmd_desautorizar))
    app.add_handler(CommandHandler("lista", cmd_lista))

    # Zonas y salidas
    app.add_handler(CommandHandler("z1", cmd_z1))
    app.add_handler(CommandHandler("z2", cmd_z2))
    app.add_handler(CommandHandler("exitz1", cmd_exitz1))
    app.add_handler(CommandHandler("exitz2", cmd_exitz2))

    # Lista espera y otros
    app.add_handler(CommandHandler("espera", cmd_espera))
    app.add_handler(CommandHandler("cambiar", cmd_cambiar))
    app.add_handler(CommandHandler("exit", cmd_exit))
    app.add_handler(CommandHandler("exitlista", cmd_exit))
    app.add_handler(CommandHandler("tomarlibre", cmd_tomarlibre))

    # Admin
    app.add_handler(CommandHandler("abrir", cmd_abrir))
    app.add_handler(CommandHandler("cerrar", cmd_cerrar))

    # Info
    app.add_handler(CommandHandler("reglas", cmd_reglas))
    app.add_handler(CommandHandler("comandos", cmd_comandos))
    app.add_handler(CommandHandler("chatid", cmd_chatid))

    logger.info("🚀 Bot iniciado...")
    app.run_polling()

if __name__ == "__main__":
    main()
