<div align="center">  
    <p align="center">
        <img src="../logo.png" alt="AURA Logo" width="230"/>
    </p>
</div>

---

## Información General

<div style="border:1px solid #ddd; border-radius:12px; padding:16px;">

**Proyecto:** AURA  
**Grupo (EV):** 4  
**Nombre del grupo:** AURA  

**Tipo de documento:** Análisis  
**Entrega:** S3  
**Versión:** v1.0 
**Fecha:** 14/04/2026  
</div>

---
## ANÁLISIS DE PRESUPUESTO
## 1. CAPEX
El CAPEX recoge la inversión inicial necesaria para desarrollar y lanzar el proyecto.

### 1.1. Coste por hora con gastos sociales

| Rol | Coste base EUR/h | +20% social | Coste real EUR/h |
|---|---|---|---|
| Developer | 30 EUR | 6 EUR | 36 EUR |
| Tech Lead | 40 EUR | 8 EUR | 48 EUR |
| Project Manager | 45 EUR | 9 EUR | 54 EUR |

### 1.2. Coste total de contratación del equipo

| Rol | Personas | Coste hora | Horas | Coste total |
|---|---|---|---|---|
| Developers | 10 | 36 EUR | 140 | 50.400 EUR |
| Tech Leads | 2 | 48 EUR | 140 | 13.440 EUR |
| Project Manager | 1 | 54 EUR | 140 | 7.560 EUR |
| **TOTAL contratación** | | | | **71.400 EUR** |

### 1.3. Coste semanal del equipo

| Rol | Personas | Coste semanal |
|---|---|---|
| Developers | 10 | 3.600 EUR |
| Tech Leads | 2 | 960 EUR |
| Project Manager | 1 | 540 EUR |
| **Total semanal** | | **5.100 EUR** |

### 1.4. Coste por fase del proyecto (teórico)

| Fase | Semanas | Coste | Coste acumulado |
|---|---|---|---|
| Devising Project | 4 | 20.400 EUR | 20.400 EUR |
| Sprint 1 | 2 | 10.200 EUR | 30.600 EUR |
| Care Workshop | 1 | 5.100 EUR | 35.700 EUR |
| Sprint 2 | 2 | 10.200 EUR | 45.900 EUR |
| Sprint 3 | 2 | 10.200 EUR | 56.100 EUR |
| PPL | 2 | 10.200 EUR | 66.300 EUR |
| WPL | 1 | 5.100 EUR | 71.400 EUR |
| **TOTAL proyecto** | **14 semanas** | **71.400 EUR** | |

### 1.5. CAPEX total del proyecto

| Concepto | Coste (EUR) | Explicación |
|---|---|---|
| Coste del equipo | 71.400 EUR | Salarios más gastos sociales (14 semanas) |
| Contingencia (20%) | 14.280 EUR | Margen para riesgos técnicos o retrasos |
| Registro de marca | 150 EUR | Tasa oficial de registro |
| **TOTAL CAPEX** | **85.830 EUR** | **Inversión inicial total del proyecto** |

---

## 2. OPEX
El OPEX recoge los costes operativos mensuales necesarios para mantener el servicio una vez lanzado.

### 2.1. OPEX fijo mensual del proyecto (ampliado)

| Concepto | Coste mensual | Explicación |
|---|---|---|
| Marketing lanzamiento | 75 EUR | Publicidad inicial y promoción |
| Dominio web | 1,67 EUR | Registro del dominio prorrateado al mes |
| GitHub Teams | 16 EUR | 4 usuarios x 4 EUR/mes |
| Servidor / hosting | 50 EUR | Alojamiento básico escalable |
| Base de datos cloud | 20 EUR | Plan gestionado de bajo coste |
| APIs de IA | 100 EUR | Consumo estimado mensual de IA |
| Internet | 50 EUR | Conexión necesaria para operaciones |
| Electricidad | 80 EUR | Consumo de equipos y periféricos |
| Agua | 20 EUR | Gasto proporcional asociado al espacio |
| Mantenimiento App | 1.326 EUR | Mantenimiento evolutivo y correctivo |
| Herramientas diseño | 15 EUR | Licencias profesionales (Figma, etc.) |
| Almacenamiento cloud | 10 EUR | Backups y recursos compartidos |
| Espacio coworking | 200 EUR | Uso ocasional de espacio profesional |
| **Total OPEX fijo** | **1.963,67 EUR** | |

### 2.2. OPEX variable
Comisión aplicada: 1,4 % + 0,25 EUR por pago. Para un plan premium de 19,90 EUR, el coste variable aproximado es de **0,53 EUR por usuario**.

---

## 3. Contextualización Temporal

### 3.1. Resumen de Inversión (CAPEX)
El CAPEX (**85.830 €**) es un coste único asociado a la fase inicial de desarrollo (14 semanas).
* **Coste semanal medio:** 5.100 €

### 3.2. Resumen Operativo (OPEX)
* **OPEX fijo mensual:** 1.963,67 € / mes
* **Fórmula general:** OPEX(n) = 1.963,67 + 0,53n (€/mes)

---

## 4. Modelado de costes en función de usuarios

### 4.1. Modelo matemático
El coste operativo mensual ($n$ = número de usuarios) se expresa como:
> **OPEX(n) = 1.963,67 + 0,53n**

### 4.2. Simulación de escenarios durante el primer año
Este cálculo suma la inversión inicial única (CAPEX) y los costes operativos de 12 meses.

| Usuarios | CAPEX | OPEX Anual | Presupuesto Total (Año 1) |
|---|---|---|---|
| 50 | 85.830,00 € | 23.882,04 € | 109.712,04 € |
| 100 | 85.830,00 € | 24.200,04 € | 110.030,04 € |
| 250 | 85.830,00 € | 25.154,04 € | 110.984,04 € |
| 500 | 85.830,00 € | 26.744,04 € | 112.574,04 € |
| 1.000 | 85.830,00 € | 29.924,04 € | 115.754,04 € |

---

## 5. Break-even point (Punto de Equilibrio)

El punto de equilibrio indica el número de usuarios necesarios para que los ingresos cubran los gastos operativos mensuales.

* **Ingreso por usuario:** 19,90 €
* **Margen neto por usuario:** 19,37 € (Ingreso - Coste Variable)
* **Cálculo:** 1.963,67 / 19,37

<div style="background-color: #0c3f81; padding: 15px; border-left: 5px solid #d2d3d2; border-radius: 4px;">
El proyecto alcanza el punto de equilibrio aproximadamente con <b>102 usuarios de pago</b>.
</div>
"""

