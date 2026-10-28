# Balanza Logigrain

Aplicación de escritorio (Python + PySide6) para el puesto de balanza de camiones:
consulta los camiones en la API de Logigrain, lee el peso del indicador por puerto serie,
registra 1° y 2° peso, envía los pesajes a la API e imprime el ticket.

Para el operador de balanza: [manual_de_instrucciones_balanza.md](manual_de_instrucciones_balanza.md).

## Puesta en marcha

```powershell
py -3.12 -m venv .venv                   # Python 3.11 o superior
.\.venv\Scripts\pip install -r requirements-dev.txt
copy config.example.toml config.toml     # ajustar puesto, puerto COM, API, impresora
.\.venv\Scripts\python -m balanza
```

Sin `config.toml` arranca con el **simulador de balanza** y la **API de prueba**, para trabajar sin hardware.

Pruebas: `.\.venv\Scripts\python -m pytest`

## Uso

Cada puesto maneja 1 o 2 cabezales (`[[balanzas]]` en `config.toml`): la balanza 1 arriba a la izquierda,
la balanza 2 arriba a la derecha.

1. Mientras el camión sube a la balanza, escribir el **CTG** y presionar `Enter`: se muestran los datos de la Carta de Porte (vehículo, mercadería,
   calada, pesos declarados), las advertencias (CPE vencida, calada no autorizada) y el **próximo paso**
   (ej. "1° PESO — BRUTO (descarga)").
2. Con el peso **ESTABLE** (verde), `F2` pesa en la balanza 1 o `F3` en la balanza 2.
   Esa balanza queda en **0** ("PESADO · BAJE EL CAMIÓN") y no permite pesar de nuevo hasta que el indicador
   baje a `umbral_cero_kg` (100 kg) o menos; desde ahí vuelve a mostrar el peso del próximo camión hasta estabilizar.
3. Al volver el camión, se vuelve a ingresar el CTG y se pesa el 2° peso (puede ser en la otra balanza):
   se calcula el neto, se envía a LogiGrain y, con su respuesta, se imprime el ticket con el **romaneo**
   (mermas y neto final). Si LogiGrain no responde, el programa pregunta si imprimir sin romaneo; el peso queda
   pendiente y se reenvía solo.
4. `Esc` limpia el CTG · `F5` imprime el último ticket · doble clic en "Pesajes de hoy" reimprime
   (con el romaneo, si llegó después).

Cada ticket se guarda también como PDF en `datos\tickets\AAAA-MM\` (ej. `BALANZA-1-000001_CTG10235570674.pdf`;
el comprobante de 1° peso lleva `_1er_peso`). Una reimpresión reemplaza el PDF por la versión actual.
Se desactiva con `guardar_pdf = false` en `[ticket]`.

El ticket imita el formato del ticket de balanza que ya se usa en el puerto (`lineas_ticket` en
`printing/ticket.py`): "Código" es el `id` de la CPE en LogiGrain, "Ingreso" la llegada al puerto
(`pos_fecha_llegada_puerto`), "F. EST-" la merma por rubros de calidad y "Merma Total" el % de mermas sobre lo
descargado (se calcula acá porque el `total_pct` de LogiGrain no siempre coincide con los kilos). "Validación" es
`codigo_validacion()`: 12 dígitos de un SHA-256 de puesto, número de pesaje, CTG, pesos y horas, más un dígito
verificador de Luhn; se recalcula desde la base para comprobar que el ticket no fue alterado.

### Simulador

El botón **Simulador** de cada balanza (`Ctrl+F2` balanza 1, `Ctrl+F3` balanza 2) cambia en caliente entre el
cabezal real (puerto serie) y el simulador; `modo` en `config.toml` es solo el modo con que abre. La balanza
simulada queda vacía hasta que se consulta un CTG: entonces sube un camión con el peso que corresponde al
próximo paso (tara entre 13.800 y 14.500 kg, bruto entre 44.000 y 45.000 kg; descarga = bruto/tara,
carga = tara/bruto), queda estable hasta que se pesa y después baja. Solo se permite con `enviar_pesos = false`
(o con la API de prueba), para no registrar pesos ficticios; la barra de estado muestra "SIMULADOR ACTIVO".

## Estructura

```
balanza/
  __main__.py          arranque, logs, armado de dependencias
  config.py            lectura de config.toml
  models.py            Camion, LecturaPeso, Pesaje (bruto/tara/neto), Envio
  api/
    cliente.py         interfaz ClienteLogigrain + cliente HTTP real   ← completar con la API real
    mock.py            API de prueba con camiones ficticios
  scale/
    parsers.py         interpretación de la trama del indicador        ← agregar parser del modelo de cabezal
    fuentes.py         puerto serie (pyserial) y simulador
    estabilidad.py     detección de peso estable
    hilo.py            lectura continua en segundo plano, reconexión automática
  services/
    pesaje.py          reglas: validaciones, 1° / 2° peso
    sync.py            envío de la cola local a la API, con reintentos y en orden
  storage/db.py        SQLite local (pesajes con su romaneo + cola de envíos)
  printing/ticket.py   ticket HTML impreso con el driver de Windows (térmica 80 mm o A4) y copia PDF
  ui/                  ventana principal, visor de peso, tareas en segundo plano
```

### Decisiones de diseño

- **Funciona sin internet**: cada pesaje se graba en SQLite junto con su envío pendiente en una misma
  transacción; el sincronizador reintenta cada `intervalo_sync_s` y respeta el orden (1° peso antes que el 2°).
  Cada envío lleva `id_local` (ej. `BALANZA-1-000123`) para que la API pueda descartar duplicados.
- **Captura segura**: solo con peso estable, lectura de menos de 3 s y sobre el peso mínimo.
  Se guarda la trama original del indicador para auditoría.
- Tras cerrar un pesaje se deselecciona el camión, para que un `F2` repetido no abra otro pesaje.

## Integración con LogiGrain

Con `[api] modo = "http"` el programa pide usuario y contraseña de LogiGrain al abrir (los completa desde `.env`:
`USUARIO_LOGIGRAIN` / `CONTRASENA_LOGIGRAIN`). Sin login válido no se entra.

| Uso | Ruta |
|---|---|
| Ingreso (token Bearer, se renueva solo al vencer) | `POST /api/v1/auth/login` |
| Puerto del usuario | `POST /api/v1/ports/my-ports` |
| Datos y validación del CTG ingresado (operación D/C, calada, 1° peso) | `POST /api/v1/cpe/get-para-pesaje` |
| Registro del peso con el `balanza_nro` de la balanza usada (la API decide si es bruto o tara); en el 2° peso devuelve el `romaneo` (neto, mermas, neto final), que se guarda en la base y se imprime | `POST /api/v1/balanza/registrar-peso` |

**`enviar_pesos = false` por defecto**: los pesos quedan en la base local pero no se registran en LogiGrain
(la barra de estado muestra "MODO PRUEBA"). Con `true` el programa no arranca si la balanza está en modo simulador,
y el botón Simulador queda deshabilitado. **Solo para pruebas**, `permitir_pesos_simulados = true` en `[api]` deja
usar el simulador con `enviar_pesos = true`: los pesos ficticios se registran en LogiGrain y la barra de estado lo
avisa en rojo.
Antes de cada envío se consulta la posición del CTG para no duplicar un peso si un envío anterior llegó pero se
perdió la respuesta.

## Pendiente

- [ ] Habilitar `enviar_pesos` cuando las balanzas estén en modo `serie` y se pruebe con un CTG de prueba.
- [ ] Modelo de cabezal: parser específico en `scale/parsers.py` y parámetros serie en `config.toml`.
- [ ] Ticket: nacionalidad del chofer (LogiGrain no la informa; hoy se omite).

## Ejecutable para los puestos

```powershell
.\construir.ps1        # corre las pruebas y genera dist\BalanzaLogigrain\
```

Copiar la carpeta `dist\BalanzaLogigrain` completa a la PC de la balanza (no hace falta instalar Python),
renombrar `config.example.toml` a `config.toml` y ajustarlo. La base de datos, los logs y los PDF de los tickets
se crean en `datos\` al lado del `.exe`. El manual del operador se copia junto al `.exe`.

**Ojo al regenerar**: PyInstaller borra `dist\BalanzaLogigrain\` completo. Si se usa esa carpeta para probar,
respaldar antes `config.toml` y `datos\`. Al actualizar un puesto, reemplazar solo el `.exe` y `_internal\`.
