# Tiempos de SPEI

Política sintética para el equipo de operaciones. Aplica a transferencias SPEI enviadas y recibidas.

## Tiempos normales de acreditación

Una transferencia SPEI se liquida normalmente en segundos y, como máximo, en unos minutos. El estado `liquidado` significa que el banco receptor ya aceptó el abono. Fuera del horario de operación del banco receptor, el abono puede verse reflejado hasta el siguiente día hábil.

## Transferencias pendientes

Un SPEI en estado `pendiente` todavía no ha sido aceptado por el banco receptor. Si sigue pendiente después de 24 horas, se considera fuera de tiempo y procede abrir una aclaración.

Los clientes suelen describirlo como "mandé dinero y no le ha llegado", "mi transferencia sigue en proceso", "ya pasó un día y no aparece" o "dice que está en tránsito".

## Qué revisar antes de responder

1. Estado del movimiento y fecha de creación.
2. Clave de rastreo, que el cliente puede usar para consultar el estado con su banco.
3. Si el SPEI está liquidado y el destinatario no lo ve, el comprobante CEP demuestra que el abono se realizó; sugerir reenviarlo.

No prometas tiempos distintos a los de esta política ni montos que no aparezcan en el movimiento.
