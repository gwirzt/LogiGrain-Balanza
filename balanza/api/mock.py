"""API de prueba con datos ficticios, para desarrollar sin conexión a LogiGrain.

Responde cualquier CTG numérico con una Carta de Porte inventada (con la misma forma que LogiGrain)
y avanza la posición del camión con cada peso enviado, para poder probar el ciclo completo."""
from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta

from ..models import Camion
from .cliente import ClienteLogigrain, ErrorApi, camion_desde_detalle, validar_ctg

log = logging.getLogger(__name__)

_GRANOS = ["Soja", "Maíz", "Trigo", "Girasol", "Sorgo"]
_DESTINATARIOS = ["EXPORTADORA DEL LITORAL S.A.", "ACOPIOS DEL SUR S.A.", "CEREALES PAMPA S.A."]


class ClienteMock(ClienteLogigrain):
    usuario = "prueba"
    puerto = "API de prueba"

    def __init__(self):
        self.enviados: list[tuple[str, dict]] = []
        self._estado: dict[str, dict] = {}  # posición y pesos por CTG

    def consultar_ctg(self, ctg: str) -> Camion:
        time.sleep(0.2)  # simula la latencia de red
        nro = validar_ctg(ctg)
        estado = self._estado.setdefault(str(nro), {"posicion": "EN_PUERTO_CALADO"})
        if estado["posicion"] == "FINALIZADO":
            raise ErrorApi(f"La CPE CTG={nro} no puede ser procesada para 'pesar en balanza': está en posición "
                           "FINALIZADO (Finalizado).", 422)
        return camion_desde_detalle(_carta_de_porte(nro, estado))

    def enviar(self, tipo: str, payload: dict) -> dict:
        log.info("[API de prueba] %s: %s", tipo, payload)
        self.enviados.append((tipo, payload))
        estado = self._estado.setdefault(str(payload["camion_id"]), {"posicion": "EN_PUERTO_CALADO"})
        if tipo == "primer_peso":
            estado.update(posicion="CON_PRIMER_PESO", peso1=payload["peso1_kg"], balanza1=payload.get("balanza_nro"),
                          momento1=payload["peso1_momento"])
        else:
            estado["posicion"] = "FINALIZADO"
        return _respuesta_registro(tipo, payload, estado["posicion"])


def _respuesta_registro(tipo: str, payload: dict, posicion: str) -> dict:
    """Misma forma que /balanza/registrar-peso. En el 2° peso agrega el romaneo con mermas de prueba."""
    segundo = tipo != "primer_peso"
    descarga = payload.get("operacion", "descarga") == "descarga"
    respuesta = {
        "success": True,
        "nro_ctg": payload["camion_id"],
        "tipo_operacion": "D" if descarga else "C",
        "tipo_peso": "BRUTO" if descarga != segundo else "TARA",
        "peso_registrado_kg": payload.get("peso2_kg" if segundo else "peso1_kg"),
        "balanza_nro": payload.get("balanza_nro"),
        "es_segundo_peso": segundo,
        "posicion_actual": posicion,
    }
    if segundo and payload.get("neto_kg") is not None:
        neto = round(payload["neto_kg"])
        volatil, rubros = round(neto * 0.001), round(neto * 0.01)
        respuesta["romaneo"] = {
            "peso_bruto_kg": payload["bruto_kg"],
            "peso_tara_kg": payload["tara_kg"],
            "peso_neto_kg": neto,
            "mermas": {"volatil_kg": volatil, "volatil_pct": 0.1, "rubros_kg": rubros, "rubros_pct": 1.0,
                       "total_kg": volatil + rubros, "total_pct": 1.1},
            "peso_neto_final_kg": neto - volatil - rubros,
            "merma_total_kg": volatil + rubros,
        }
    return respuesta


def _carta_de_porte(nro: int, estado: dict) -> dict:
    rng = random.Random(nro)  # mismo CTG, mismos datos
    grano = rng.choice(_GRANOS)
    destinatario = rng.choice(_DESTINATARIOS)
    bruto = rng.randrange(44_000, 45_001, 20)
    tara = rng.randrange(13_800, 14_501, 20)
    tipo_operacion = rng.choice(["C", "D"])  # mismo CTG, misma operación
    con_primero = estado["posicion"] == "CON_PRIMER_PESO"
    # El 1° peso de balanza es el bruto en descarga (entra lleno) y la tara en carga (entra vacío).
    primero = "bruto" if tipo_operacion == "D" else "tara"
    pesos_balanza = {}
    for campo in ("bruto", "tara"):
        registrado = con_primero and campo == primero
        pesos_balanza[f"peso_{campo}_balanza"] = estado.get("peso1") if registrado else None
        pesos_balanza[f"balanza_nro_{campo}"] = estado.get("balanza1") if registrado else None
        pesos_balanza[f"pos_fecha_peso_{campo}"] = estado.get("momento1") if registrado else None
    return {
        "nro_ctg": nro,
        "sucursal": rng.randint(1, 99),
        "nro_orden": rng.randint(1000, 99999),
        "estado": "CF",
        "fecha_vencimiento": (datetime.now() + timedelta(days=2)).isoformat(timespec="seconds"),
        "codigo_turno": datetime.now().strftime("%Y%m%d") + f"{rng.randint(1, 999999):06d}",
        "regimen_descripcion": "Pérdida de Identidad",
        "observaciones": "Datos de prueba",
        "dominio": f"AB{rng.randint(100, 999)}CD,AE{rng.randint(100, 999)}FG",
        "transportista_nombre": "TRANSPORTES DE PRUEBA S.R.L.",
        "cuit_transportista": 30700000001,
        "chofer_nombre": "CHOFER DE PRUEBA",
        "cuit_chofer": 20300000001,
        "nombre_grano": grano,
        "cosecha": 2526,
        "tipo_operacion": tipo_operacion,
        "origen_nombre": "PRODUCTOR DE PRUEBA",
        "destinatario_razon_social": destinatario,
        "intervinientes": {"representante_entregador_nombre": "ENTREGADOR DE PRUEBA"},
        "calada_estado": "A",
        "calada_humedad_pct": 13.5,
        "calada_grado": "2",
        "calada_pct_total": 0.0,
        "mercaderia_fumigada": False,
        "peso_bruto": bruto,
        "peso_tara": tara,
        "peso_neto": bruto - tara,
        **pesos_balanza,
        "posicion_actual": estado["posicion"],
        "posicion_label": "Con primer peso" if con_primero else "En puerto calado",
        "puede_pesar": True,
    }
