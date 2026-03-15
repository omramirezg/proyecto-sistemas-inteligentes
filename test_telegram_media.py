"""
Test rápido para diagnosticar por qué las imágenes y audios
no se muestran correctamente en Telegram.
"""
import sys, io, asyncio
sys.path.insert(0, 'src')

from config_loader import ConfigLoader
from telegram_bot import TelegramNotificador

config = ConfigLoader()
config.configurar_logging()
telegram = TelegramNotificador(config)

# Chat ID de prueba (del registro)
import json
with open('data/registro_usuarios.json', 'r') as f:
    registros = json.load(f)
    chat_id = list(registros.values())[0]
    print(f"Chat ID de prueba: {chat_id}")


async def test_imagen():
    """Test 1: Enviar una imagen PNG simple con fondo BLANCO."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.plot([1, 2, 3, 4, 5], [10, 20, 15, 25, 30], 'b-o', linewidth=2)
    ax.set_title('Test Imagen - Fondo Blanco', color='black')
    ax.set_xlabel('X', color='black')
    ax.set_ylabel('Y', color='black')
    ax.tick_params(colors='black')

    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    imagen_bytes = buf.getvalue()
    print(f"Imagen generada: {len(imagen_bytes)} bytes ({len(imagen_bytes)/1024:.1f} KB)")

    # Enviar
    bot = await telegram._obtener_bot()
    img_file = io.BytesIO(imagen_bytes)
    img_file.name = 'test_blanco.png'
    img_file.seek(0)
    await bot.send_photo(chat_id=chat_id, photo=img_file, caption="TEST 1: imagen PNG fondo blanco")
    print("✅ Imagen PNG enviada")


async def test_audio_ogg():
    """Test 2: Enviar audio OGG_OPUS desde Google Cloud TTS."""
    try:
        from google.cloud import texttospeech
        client = texttospeech.TextToSpeechClient()

        synthesis_input = texttospeech.SynthesisInput(
            text="Hola, esta es una prueba del sistema de alertamiento."
        )
        voice = texttospeech.VoiceSelectionParams(
            language_code="es-US",
            name="es-US-Neural2-A",
        )
        # Test con OGG_OPUS (formato actual)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.OGG_OPUS,
            speaking_rate=1.0,
            pitch=0.0,
            volume_gain_db=2.0,
        )
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        audio_bytes = response.audio_content
        print(f"Audio OGG generado: {len(audio_bytes)} bytes ({len(audio_bytes)/1024:.1f} KB)")

        # Verificar los primeros bytes (OGG debe empezar con 'OggS')
        print(f"Primeros 4 bytes (OGG header): {audio_bytes[:4]}")

        bot = await telegram._obtener_bot()
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = 'test.ogg'
        audio_file.seek(0)
        await bot.send_voice(chat_id=chat_id, voice=audio_file, caption="TEST 2: audio OGG_OPUS")
        print("✅ Audio OGG enviado con send_voice")

    except Exception as e:
        print(f"❌ Error audio OGG: {e}")


async def test_audio_mp3():
    """Test 3: Enviar audio MP3 desde Google Cloud TTS."""
    try:
        from google.cloud import texttospeech
        client = texttospeech.TextToSpeechClient()

        synthesis_input = texttospeech.SynthesisInput(
            text="Prueba en formato MP3. La temperatura es 45 grados y la presión es 30 PSI."
        )
        voice = texttospeech.VoiceSelectionParams(
            language_code="es-US",
            name="es-US-Neural2-A",
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0,
            pitch=0.0,
            volume_gain_db=2.0,
        )
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        audio_bytes = response.audio_content
        print(f"Audio MP3 generado: {len(audio_bytes)} bytes ({len(audio_bytes)/1024:.1f} KB)")

        bot = await telegram._obtener_bot()
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = 'test.mp3'
        audio_file.seek(0)
        await bot.send_audio(chat_id=chat_id, audio=audio_file, caption="TEST 3: audio MP3",
                             title="Prescripción IA")
        print("✅ Audio MP3 enviado con send_audio")

    except Exception as e:
        print(f"❌ Error audio MP3: {e}")


async def main():
    print("=" * 50)
    print("DIAGNÓSTICO DE MEDIOS EN TELEGRAM")
    print("=" * 50)

    print("\n--- Test 1: Imagen PNG (fondo blanco) ---")
    await test_imagen()
    await asyncio.sleep(2)

    print("\n--- Test 2: Audio OGG_OPUS (send_voice) ---")
    await test_audio_ogg()
    await asyncio.sleep(2)

    print("\n--- Test 3: Audio MP3 (send_audio) ---")
    await test_audio_mp3()

    print("\n" + "=" * 50)
    print("Revisa Telegram y dime cuáles funcionan correctamente.")


asyncio.run(main())
