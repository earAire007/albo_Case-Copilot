# Comprobante CEP

Política sintética sobre el Comprobante Electrónico de Pago (CEP) de transferencias SPEI.

## Qué es el CEP

El CEP es la constancia oficial de que una transferencia SPEI fue liquidada en la cuenta del beneficiario. Solo existe para movimientos en estado `liquidado`; un SPEI pendiente o devuelto no tiene CEP.

Los clientes lo piden como "necesito el comprobante de mi transferencia", "el destinatario dice que no le llegó y quiero demostrar que pagué", "mándame el recibo del pago" o "no encuentro la constancia".

## Reenvío del comprobante

Si el movimiento está liquidado y tiene CEP disponible, la acción es reenviar el comprobante al cliente. El reenvío no modifica el movimiento ni su estado.

Para identificar el movimiento basta la clave de rastreo o el identificador interno. No es necesario solicitar datos adicionales al cliente.

## Límites

1. No se genera CEP para transferencias pendientes: primero debe liquidarse.
2. Si el movimiento está liquidado pero el CEP no está disponible, informar al cliente y escalar a operaciones.
3. El CEP muestra datos enmascarados del ordenante y del beneficiario; no se agregan datos completos al reenviarlo.

Un CEP demuestra el pago, pero no obliga al destinatario a reconocerlo.
