from datetime import datetime

from balanza.api.cliente import camion_desde_detalle
from balanza.api.mock import ClienteMock
from balanza.ficha import armar_ficha, proximo_paso

# Recorte de la respuesta real de get-para-pesaje para el CTG 10235570674.
CPE = {
    "nro_ctg": 10235570674, "sucursal": 39, "nro_orden": 15746, "estado": "CF",
    "fecha_vencimiento": "2026-10-17T19:53:07", "observaciones": "20261014092587 - Cosecha 2025-2026 -   Ctto SOJA-DEPOSITO-U6",
    "nombre_grano": "Soja", "chofer_nombre": "CUIT 20266609036", "transportista_nombre": "SOSA ARIEL ALEJANDRO",
    "destinatario_razon_social": "UNION AGRICOLA DE AVELLANEDA", "regimen_descripcion": "Pérdida de Identidad",
    "cosecha": 2526, "peso_bruto": 52280, "peso_tara": 16140, "peso_neto": 36140, "tipo_operacion": "D",
    "peso_bruto_balanza": None, "peso_tara_balanza": None, "dominio": "HDD168,AH929CH",
    "cuit_chofer": 20266609036, "cuit_transportista": 23258889819, "codigo_turno": "20261014092587",
    "mercaderia_fumigada": True, "origen_nombre": "UNION AGRICOLA DE AVELLANEDA COOP LTDA", "calada_estado": "A",
    "calada_humedad_pct": 13.0, "calada_pct_total": 1.0, "calada_grado": 0, "posicion_actual": "EN_PUERTO_CALADO",
    "posicion_label": "En puerto calado", "puede_pesar": True,
    "intervinientes": {"representante_entregador_nombre": "GUALTIERI E HIJOS SOCIEDAD DE RESPONSABILIDAD LIMITADA"},
}


def valores(ficha):
    return {f"{s}/{e}": v for s, filas in ficha.secciones for e, v in filas}


def test_ficha_ctg_real():
    camion = camion_desde_detalle(CPE)
    ficha = armar_ficha(camion, ahora=datetime(2026, 10, 27, 12, 0))
    v = valores(ficha)
    assert ficha.proximo.startswith("1° PESO — BRUTO")
    assert v["Carta de Porte/CPE N°"] == "00039-00015746"
    assert v["Carta de Porte/Vencimiento"].endswith("(VENCIDA)")
    assert v["Vehículo/Patente"] == "HDD168" and v["Vehículo/Acoplado"] == "AH929CH"
    assert v["Vehículo/Chofer"] == "CUIT 20266609036"  # sin nombre: no repite el CUIT
    assert v["Vehículo/Transportista"] == "SOSA ARIEL ALEJANDRO (CUIT 23258889819)"
    assert v["Mercadería/Grano"] == "Soja · cosecha 2025/26"
    assert v["Calada/Estado"] == "Autorizada" and v["Calada/Fumigada"] == "Sí"
    assert "52.280 kg" in v["Pesos/Declarado en CPE"]
    assert ficha.advertencias == ["La Carta de Porte venció el 17/10/2026 19:53."]


def test_proximo_paso_segun_posicion_y_operacion():
    descarga_1 = camion_desde_detalle(CPE)
    descarga_2 = camion_desde_detalle({**CPE, "posicion_actual": "CON_PRIMER_PESO", "peso_bruto_balanza": 52000})
    carga_1 = camion_desde_detalle({**CPE, "tipo_operacion": "C"})
    assert proximo_paso(descarga_1) == (1, "BRUTO")
    assert proximo_paso(descarga_2) == (2, "TARA")
    assert proximo_paso(carga_1) == (1, "TARA")
    assert "52.000 kg" in valores(armar_ficha(descarga_2))["Pesos/1° peso en balanza"]


def test_calada_no_autorizada_avisa():
    ficha = armar_ficha(camion_desde_detalle({**CPE, "calada_estado": "D", "fecha_vencimiento": None}))
    assert ficha.advertencias == ["Calada Demorada."]


def test_mock_avanza_posicion():
    api = ClienteMock()
    c = api.consultar_ctg("123")
    assert c.posicion == "EN_PUERTO_CALADO"
    api.enviar("primer_peso", {"camion_id": "123", "peso1_kg": 50000, "balanza_nro": 1, "peso1_momento": None})
    c = api.consultar_ctg("123")
    assert (c.posicion, c.primer_peso_kg, c.primer_peso_balanza_nro) == ("CON_PRIMER_PESO", 50000, 1)
