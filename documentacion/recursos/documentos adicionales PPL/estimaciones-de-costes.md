# **Estimaciones de costes**
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

**Tipo de documento:** Documento adicional de análisis  
**Entrega:** PPL   
**Versión:** v1.0   
**Fecha:** 27/04/2026  
</div>

---

## 1. Contenido
Este documento contiene la estimación de coste del proyecto durante la etapa de PPL. Conteniendo además los posibles riesgos a enfrentar durante el proyecto en esta etapa de desarrollo y las consecuencias a largo plazo que estas desencadenarían. 

Esta estimación saldrá del contraste de dos escenarios extremos posibles. El escenario negativo, escenario donde todos los riesgos observados ocurren, y el escenario positivo, donde ningun riesgo aparece y todo se desarrolla a la perfección. 

---

## 2. Riesgos
En la etapa de PPL surgirán nuevos riesgos que pueden impactar de forma negativa a la estimacion de costes del proyecto. Los riesgos observados son los siguientes:

- **Errores no detectados en la aplicación:** Pueden surgir fallos no previstos durante la fase de pruebas de la aplicación, lo cual obliga a incrementar el rendimiento al realizar las correcciones necesarias para el correcto funcionamiento de la aplicación, lo que incrementa las horas de trabajo del equipo, traducido en el aumento de costes. 

- **Fallos en servicios externos:** Posible fallo, limitación o indisponibilidad de servicios externos necesarios para el funcionamiento de la aplicación, en este caso de las APIs usadas. Además, el aumento en el uso de estos servicios puede requerir la contratación de planes superiores, llevando a un aumento de costes tanto en horas invertidas para corregirlo como en el pago de planes de mayor cantidad de usos en esas APIs. 

- **Problemas de rendimiento del equipo:** Existe el riesgo de que el equipo no llegue a conseguir el rendimiento esperado debido a diversos factores como la sobrecarga de trabajo o una mala organización. Esto puede provocar una disminución en la productividad durante el desarrollo. La solución a ello llevaría a un mayor esfuerzo en horas traducido en aumento de costes. 

- **Campaña de marketing ineficaz:** La estrategia de marketing puede no lograr el impacto deseado en el público objetivo, lo que reduce la visibilidad y el alcance del producto en el momento del lanzamiento. Para solucionarlo se necesita ajustar la estrategia, lo que implica una mayor inversión económica. 

- **Retraso en el lanzamiento:** Existe la posibilidad de no conseguir realizar el lanzamiento al completo en la fecha prevista debido a problemas técnicos, organizativos o dependencias externas, lo que impide mantener el transcurso natural del proyecto. Para solucionarlo se aumentarán los costes al mantenerse en el tiempo el trabajo realizado por el equipo. 

---

## 3. CAPEX
El CAPEX recoge la inversión inicial necesaria para desarrollar y lanzar el proyecto.

### Coste semanal del equipo

| Rol | Personas | Coste semanal |
|---|---|---|
| Developers | 10 | 3.600 EUR |
| Tech Leads | 2 | 960 EUR |
| Project Manager | 1 | 540 EUR |
| **Total semanal** | | **5.100 EUR** |

Teniendo en cuenta las dos semanas de duración del PPL (10.200 EUR) y el 20% de contingencia (2.040 EUR) nos da un total de 12.240 EUR

---

## 4. OPEX
El OPEX recoge los costes operativos mensuales necesarios para mantener el servicio una vez lanzado.

### OPEX fijo mensual del proyecto 

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



---

## 5. Estimación final

A continuación se establecen los dos casos hipotéticos mencionados anteriormente para poder hacer la comparación sintetizada de ambos. 

- **Escenario positivo**: Se basaría en el CAPEX inicial más la suma progresiva del OPEX mensual sin ninguna variante añadida, pues no ha aparecido ningun riesgo que perjudique económicamente. Siendo 14.203,67 EUR el monto del mes inicial, sumándose 1963 EUR de forma mensual.

- **Escenario negativo**: Habrá que tener en cuenta los distintos riesgos si se cumplen;  casi todos los riesgos definidos implican un esfuerzo extra en horas, así que tomaremos un 40% de horas extra respecto a las establecidas de inicio (dado que el 40% de los 10.200 EUR serían 4.080 EUR más contingencia inicial), sería un total de 16.320 EUR. También teniendo en cuenta el gasto mensual extra en conseguir un uso menos limitado de las API usando sus versiones de pago superior sería de un estimado de 170 EUR mensuales respecto a los 100 EUR estimados, llevando el OPEX mensual a 2033,67 EUR mensuales. Esto nos deja que el monto del primer mes es de 18.353,67 EUR, sumándose 2033,67 EUR de forma mensual.

<div align="center">  
    <p align="center">
        <img src="../documentos adicionales PPL/imgs/edc1.png/" alt="imagen comparativa estimacion de costes"/>
    </p>
</div>

