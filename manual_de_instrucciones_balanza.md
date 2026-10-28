# Manual de instrucciones — Balanza Logigrain

Este manual explica cómo usar el programa del puesto de balanza para pesar camiones, imprimir los tickets y
qué hacer cuando aparece un aviso. Al final hay un anexo para quien instala y configura el programa.

---

## 1. Abrir el programa e ingresar

1. Abra **BalanzaLogigrain** (el ícono o el archivo `BalanzaLogigrain.exe`).
2. Aparece la pantalla **Ingreso**. Escriba su **usuario** y **contraseña de LogiGrain** y presione **Ingresar**.
   - Si los datos ya aparecen completos, solo presione **Ingresar**.
   - Si el usuario o la contraseña no son correctos, el programa lo avisa en rojo y no deja entrar.
3. Se abre la pantalla principal.

## 2. La pantalla principal

| Zona | Qué muestra |
|---|---|
| **Arriba: BALANZA 1 (izquierda) y BALANZA 2 (derecha)** | El peso en tiempo real de cada balanza, su estado y el botón para pesar. Si el puesto tiene una sola balanza, se ve solo la de la izquierda. |
| **Centro: Carta de Porte** | El casillero para escribir el **CTG**, el **próximo paso** (en letras grandes) y los datos de la Carta de Porte. |
| **Abajo: Pesajes de hoy** | Todos los pesajes del día, con su 1° peso, 2° peso, neto y estado. |
| **Barra inferior** | Envíos pendientes a LogiGrain, el usuario, el puerto, el puesto y los avisos de modo prueba o simulador. |

### Estado de cada balanza

| Lo que se ve | Significa |
|---|---|
| **ESTABLE** (verde) | El peso está quieto. Ya se puede pesar. |
| **EN MOVIMIENTO** (amarillo) | El camión todavía se está acomodando. Espere. |
| **PESADO · BAJE EL CAMIÓN** (gris, en 0 kg) | Ya se registró el peso. La balanza no deja pesar de nuevo hasta que el camión baje. |
| **SIN CONEXIÓN** (rojo) | El programa no recibe datos del indicador de la balanza (ver sección 7). |

## 3. Pesar un camión

Cada camión se pesa **dos veces**: al entrar y al salir. El programa sabe cuál de los dos pesos corresponde.

| Operación | 1° peso (al entrar) | 2° peso (al salir) |
|---|---|---|
| **Descarga** (entra lleno, sale vacío) | BRUTO | TARA |
| **Carga** (entra vacío, sale lleno) | TARA | BRUTO |

### Paso a paso

1. Mientras el camión sube a la balanza, escriba el número de **CTG** y presione **Enter**.
2. El programa consulta LogiGrain y muestra:
   - el **próximo paso**, por ejemplo **"1° PESO — BRUTO (descarga)"**;
   - los datos de la Carta de Porte: patente, chofer, grano, destinatario, calada y pesos declarados;
   - las **advertencias en rojo**, si las hay (Carta de Porte vencida, calada no autorizada, etc.). Léalas antes de pesar.
3. Espere a que la balanza donde está el camión marque **ESTABLE** (verde).
4. Presione **F2** si el camión está en la **balanza 1** o **F3** si está en la **balanza 2**.
   También puede hacer clic en el botón **Pesar en balanza 1 / 2**.
5. El programa confirma el peso en verde, por ejemplo: *"✔ CTG 10235570674: 1° peso 41.200 kg en balanza 1."*
   - Esa balanza queda en **0** hasta que el camión baje.
   - El casillero del CTG queda vacío, listo para el próximo camión.
6. **Cuando el camión vuelve**, repita los mismos pasos con el mismo CTG. Ese será el **2° peso**.
   Puede hacerse en la misma balanza o en la otra.

> Mientras un camión baja, ya puede escribir el CTG del siguiente.

## 4. El ticket

### Al terminar el 2° peso

1. El programa registra el 2° peso en LogiGrain y muestra *"Enviando a LogiGrain para el romaneo…"*.
2. LogiGrain responde con el **romaneo**: el neto, las mermas y el **neto final**.
3. Se abre la **vista previa** del ticket. Desde ahí se imprime.

El ticket tiene el mismo formato que el que ya se usaba en el puerto:

| Línea | Qué es |
|---|---|
| Chofer / Cuit | Datos del chofer según la Carta de Porte. Si LogiGrain no tiene el nombre, queda solo el CUIT. |
| Ingreso / Salio | Llegada al puerto (según LogiGrain) y hora del 2° peso. |
| Fecha | Hora del 2° peso. |
| Operador | Usuario de LogiGrain que tomó el peso. |
| C. P. / Código | Número de CTG / número del camión en LogiGrain. |
| Patente / Producto | Según la Carta de Porte. |
| Bruto / Tara | Pesos de balanza. |
| Desc. (o Carg. en una carga) | Kilos descargados (o cargados): bruto menos tara. |
| Mermas | Total de mermas del romaneo de LogiGrain. |
| F. EST- | Merma fuera de estándar de calidad (rubros). |
| Neto | Neto final: descargado menos mermas. |
| Balanza | Número de balanza. "Modo Automatico" = peso leído del indicador; "Modo Simulador" = peso simulado (pruebas). |
| Liq:Grado | Grado de calada. |
| Merma Total | Porcentaje de merma sobre lo descargado. |
| Validación | Código de control del ticket (ver abajo). |

Si el ticket sale sin romaneo, en lugar de Mermas, F. EST-, Neto y Merma Total dice
**"Mermas : pendiente (sin romaneo de LogiGrain)"**.

**Código de validación:** son 13 números que el programa calcula con los datos del pesaje (puesto, número,
CTG, pesos y horas). Si alguien modifica a mano un peso o una hora en el ticket, el código ya no coincide
con el que da el programa para ese pesaje. El último número es un dígito verificador, que detecta un número
mal copiado.

### Si LogiGrain no responde

Si no hay conexión con LogiGrain, aparece el aviso **"LogiGrain no respondió"** con esta pregunta:
*¿Imprimir el ticket ahora, sin el romaneo?*

- **Sí**: se imprime el ticket con los pesos y el neto de balanza, sin mermas ni neto final.
- **No**: el ticket no se imprime ahora. Puede imprimirlo más tarde (ver *Reimprimir*). Cuando LogiGrain reciba
  el peso, el ticket ya sale con el romaneo.

En los dos casos **el peso no se pierde**: queda guardado y se envía solo cuando vuelve la conexión (sección 5).

### Comprobante de 1° peso

Si hace falta, después del 1° peso puede imprimir un **comprobante de 1° pesaje** con **F5**.

### Reimprimir

- **F5** imprime de nuevo el último ticket.
- **Doble clic** sobre un pesaje de la lista **Pesajes de hoy** reimprime ese ticket.
- La lista muestra solo los pesajes del día.

### Copia en PDF

Cada vez que se imprime un ticket, el programa guarda además una **copia en PDF**, aunque se cancele la vista
previa. Las copias quedan en la carpeta del programa:

```
datos\tickets\2026-10\BALANZA-1-000001_CTG10235570674.pdf
datos\tickets\2026-10\BALANZA-1-000002_CTG10235570675_1er_peso.pdf   (comprobante de 1° peso)
```

Hay una carpeta por mes. Si se reimprime un ticket, el PDF se reemplaza por la versión más nueva; por ejemplo,
la que ya tiene el romaneo.

## 5. Si se corta la conexión con LogiGrain

- **Los pesos no se pierden.** Cada peso se guarda primero en la computadora del puesto y después se envía a LogiGrain.
- El programa **reintenta solo** cada 30 segundos, respetando el orden (nunca envía un 2° peso antes que su 1°).
  Esto sigue funcionando aunque cierre el programa o se apague la computadora: al volver a abrirlo, sigue enviando.
- En la barra inferior, **Envíos pendientes: N** indica cuántos pesos faltan enviar.
  - En **rojo** significa que hay envíos sin entrar. Pase el mouse por encima para ver el motivo.
  - **Envíos pendientes: 0** significa que todo está en LogiGrain.
- Puede seguir pesando normalmente mientras no hay conexión.

**Avise a sistemas** si los envíos pendientes no bajan después de que vuelve la conexión, o si el motivo que
aparece no es un problema de conexión (por ejemplo, LogiGrain rechaza el peso de un CTG). En ese caso, los pesos
que vienen después quedan esperando detrás de ese envío.

## 6. Atajos de teclado

| Tecla | Acción |
|---|---|
| **Enter** | Consultar el CTG escrito |
| **Esc** | Limpiar el CTG y la Carta de Porte |
| **Ctrl+F** | Ir al casillero del CTG |
| **F2** | Pesar en la balanza 1 |
| **F3** | Pesar en la balanza 2 |
| **F5** | Imprimir de nuevo el último ticket |
| **Ctrl+F2 / Ctrl+F3** | Activar o desactivar el simulador de la balanza 1 / 2 (solo para pruebas) |

## 7. Mensajes y avisos

| Mensaje | Qué hacer |
|---|---|
| *El peso no está estable. Espere a que se estabilice.* | Espere a que la balanza marque **ESTABLE** y vuelva a pesar. |
| *El peso (…) es menor al mínimo permitido* | La balanza está vacía o el camión no subió del todo. |
| *La lectura de la balanza está desactualizada* | El indicador dejó de mandar datos. Revise el indicador y el cable. |
| **SIN CONEXIÓN** en una balanza | Revise que el indicador esté encendido y el cable conectado. El programa se reconecta solo. Si sigue así, avise a sistemas. |
| *No se puede pesar: …* al consultar el CTG | LogiGrain no permite pesar ese CTG (por ejemplo, ya está finalizado o no tiene la calada). Lea el motivo y consulte con el supervisor. |
| *No se pudo consultar el CTG* | No hay conexión con LogiGrain. Reintente en unos minutos. |
| ⚠ *La Carta de Porte venció el …* | La CPE está vencida. Consulte con el supervisor antes de pesar. |
| ⚠ *Calada Demorada / Rechazada* | La calada no está autorizada. Consulte con el supervisor. |
| ⚠ *LogiGrain indica que esta Carta de Porte no se puede pesar* | No pese el camión. Consulte con el supervisor. |
| **LogiGrain no respondió** (al terminar el 2° peso) | Ver *Si LogiGrain no responde* en la sección 4. |
| **MODO PRUEBA: los pesos no se envían a LogiGrain** | El programa está configurado para pruebas. Los pesos **no** quedan registrados en LogiGrain. Avise a sistemas si no debería estar así. |
| **SIMULADOR ACTIVO** | Alguna balanza muestra pesos simulados, no los de la balanza real. **No use el programa para pesar camiones reales.** |
| **SIMULADOR ACTIVO: SE ENVÍAN PESOS FICTICIOS A LOGIGRAIN** (rojo) | Configuración solo para pruebas: los pesos simulados quedan registrados en LogiGrain. **No pese camiones reales.** Avise a sistemas. |

---

## Anexo para el administrador

### Instalación

1. Copie la carpeta **`BalanzaLogigrain`** completa a la computadora del puesto. No hace falta instalar Python.
2. Renombre `config.example.toml` a **`config.toml`** y ajústelo (ver abajo).
3. Opcional: cree un archivo **`.env`** junto al `.exe` para que la pantalla de ingreso aparezca completa:
   ```
   USUARIO_LOGIGRAIN=usuario
   CONTRASENA_LOGIGRAIN=contraseña
   ```
4. El programa crea solo la carpeta **`datos\`**, con la base de pesajes (`balanza.db`), los registros
   (`balanza.log`) y los PDF de los tickets (`tickets\`).

### Configuración (`config.toml`)

| Clave | Para qué sirve |
|---|---|
| `puesto` | Nombre del puesto. Aparece en el número de ticket (ej. `BALANZA-1-000001`). |
| `peso_minimo_kg` | No deja pesar por debajo de este valor. |
| `[[balanzas]]` | Un bloque por balanza (1 o 2). `nro` es el número que se informa a LogiGrain; `puerto` y `baudios` son los del indicador. |
| `modo` (en cada balanza) | `"serie"` para la balanza real, `"simulador"` para probar. Es solo el modo con que abre: en pantalla se cambia con **Ctrl+F2 / Ctrl+F3**. |
| `[api] url_base` | Dirección de LogiGrain. |
| `enviar_pesos` | `true` registra los pesos en LogiGrain. Con `false` el programa funciona en **modo prueba**. |
| `permitir_pesos_simulados` | **Solo para pruebas.** Con `true` deja usar el simulador aunque `enviar_pesos = true`, y los pesos ficticios quedan registrados en LogiGrain. Volver a `false` (o borrarlo) antes de operar. |
| `intervalo_sync_s` | Cada cuántos segundos se reintentan los envíos pendientes (30 por defecto). |
| `[ticket] impresora` | Nombre de la impresora. Vacío usa la predeterminada de Windows. |
| `ancho_mm`, `alto_mm` | Tamaño del ticket: 80 mm para impresora térmica, 210 para A4. |
| `empresa` | Nombre que encabeza el ticket. |
| `vista_previa` | `true` muestra la vista previa antes de imprimir. |
| `guardar_pdf` | `true` guarda una copia PDF de cada ticket en `datos\tickets\`. |

Por seguridad, si alguna balanza está en simulador con `enviar_pesos = true` y sin `permitir_pesos_simulados`,
el programa no arranca y muestra el aviso **Configuración insegura**.

### Copias de seguridad

Respalde periódicamente la carpeta **`datos\`**: tiene todos los pesajes, los envíos pendientes y los PDF de
los tickets.

### Actualizar el programa

Para instalar una versión nueva, reemplace **solo** `BalanzaLogigrain.exe` y la carpeta `_internal\`.
**No borre ni reemplace `config.toml`, `.env` ni la carpeta `datos\`.** Si reemplaza la carpeta completa,
se pierden la configuración del puesto, los pesajes, los envíos pendientes y los tickets guardados.
