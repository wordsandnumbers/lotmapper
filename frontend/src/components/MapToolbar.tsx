export type EditorMode = 'select' | 'edit' | 'draw' | 'split' | 'editBoundary' | 'redrawBoundary'

interface MapToolbarProps {
  mode: EditorMode
  onModeChange: (mode: EditorMode) => void
  selectionCount: number
  canEdit: boolean
  boundaryModified: boolean
  onSaveBoundary: () => void
  onDiscardBoundary: () => void
  onDelete: () => void
  onMerge: () => void
}

export default function MapToolbar({
  mode,
  onModeChange,
  selectionCount,
  canEdit,
  boundaryModified,
  onSaveBoundary,
  onDiscardBoundary,
  onDelete,
  onMerge,
}: MapToolbarProps) {
  const modeBtn = (label: string, targetMode: EditorMode, disabled = false) => (
    <button
      key={targetMode}
      onClick={() => onModeChange(targetMode)}
      disabled={disabled}
      title={label}
      className={`px-3 py-1.5 text-xs font-medium rounded transition-colors whitespace-nowrap ${
        mode === targetMode
          ? 'bg-brand-primary text-white shadow-inner'
          : 'text-app-heading hover:bg-gray-100'
      } disabled:opacity-40 disabled:cursor-not-allowed`}
    >
      {label}
    </button>
  )

  const actionBtn = (label: string, onClick: () => void, disabled: boolean, danger = false) => (
    <button
      key={label}
      onClick={onClick}
      disabled={disabled}
      title={label}
      className={`px-3 py-1.5 text-xs font-medium rounded whitespace-nowrap transition-colors ${
        danger
          ? 'text-red-600 hover:bg-red-50'
          : 'text-app-heading hover:bg-gray-100'
      } disabled:opacity-40 disabled:cursor-not-allowed`}
    >
      {label}
    </button>
  )

  return (
    <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000] flex gap-2 pointer-events-none select-none">
      {canEdit && (
        <div className="flex items-center gap-0.5 bg-white shadow-md rounded-lg px-1 py-1 ring-1 ring-black/10 pointer-events-auto">
          {/* Selection & editing modes */}
          {modeBtn('Select', 'select')}
          {modeBtn('Edit Points', 'edit', selectionCount !== 1)}
          {modeBtn('Draw', 'draw')}
          {modeBtn('Split', 'split', selectionCount !== 1)}

          <div className="w-px h-4 bg-gray-200 mx-0.5" />

          {/* Bulk actions */}
          {actionBtn('Merge', onMerge, selectionCount < 2)}
          {actionBtn('Delete', onDelete, selectionCount === 0, true)}
        </div>
      )}

      {canEdit && (
        <div className="flex items-center gap-0.5 bg-white shadow-md rounded-lg px-1 py-1 ring-1 ring-black/10 pointer-events-auto">
          {modeBtn('Edit Boundary', 'editBoundary')}
          {modeBtn('Redraw Boundary', 'redrawBoundary')}
          {boundaryModified && (
            <>
              <div className="w-px h-4 bg-gray-200 mx-0.5" />
              <button
                onClick={onSaveBoundary}
                className="px-3 py-1.5 text-xs font-medium rounded whitespace-nowrap bg-green-600 text-white hover:bg-green-700 transition-colors"
              >
                Save Boundary
              </button>
              <button
                onClick={onDiscardBoundary}
                className="px-3 py-1.5 text-xs font-medium rounded whitespace-nowrap text-app-heading hover:bg-gray-100 transition-colors"
              >
                Discard
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
