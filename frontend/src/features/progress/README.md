# features/progress

Reservada. O serviço e os hooks de progresso (`putProgress`, `getProgress`, `listContinue`, `useProgressSaver`) ficam em `src/shared/progress/` porque são usados por `library` e `reader-manga`, e uma feature não pode importar outra. Só crie código aqui se surgir uma tela própria de progresso.
