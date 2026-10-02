import React from 'react'

export interface Column<T> {
  header: string
  accessor: keyof T | ((row: T) => React.ReactNode)
  align?: 'left' | 'center' | 'right'
}

export interface DataTableProps<T> {
  columns: Column<T>[]
  data: T[]
  keyExtractor: (row: T) => string
}

export function DataTable<T>({ columns, data, keyExtractor }: DataTableProps<T>) {
  if (data.length === 0) {
    return (
      <div className="p-8 text-center text-xs text-slate-500 bg-dark-card border border-dark-border rounded-2xl">
        No records available
      </div>
    )
  }

  return (
    <div className="overflow-x-auto bg-dark-card border border-dark-border rounded-2xl shadow-xl">
      <table className="w-full text-xs text-left">
        <thead className="bg-dark-elevated border-b border-dark-border text-slate-400 uppercase font-bold tracking-wider">
          <tr>
            {columns.map((col, idx) => (
              <th
                key={idx}
                className={`px-4 py-3.5 ${
                  col.align === 'right'
                    ? 'text-right'
                    : col.align === 'center'
                    ? 'text-center'
                    : 'text-left'
                }`}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-dark-border">
          {data.map((row) => (
            <tr key={keyExtractor(row)} className="hover:bg-dark-elevated/40 transition-colors">
              {columns.map((col, idx) => (
                <td
                  key={idx}
                  className={`px-4 py-3.5 ${
                    col.align === 'right'
                      ? 'text-right'
                      : col.align === 'center'
                      ? 'text-center'
                      : 'text-left'
                  }`}
                >
                  {typeof col.accessor === 'function'
                    ? col.accessor(row)
                    : (row[col.accessor] as unknown as React.ReactNode)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

