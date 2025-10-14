import { useState, useEffect } from 'react';

interface UseTablePageSizeOptions {
  /**
   * Height of each table row in pixels (including borders/padding)
   * Default: 52px (Material-UI DataGrid default row height)
   */
  rowHeight?: number;
  
  /**
   * Height reserved for the table header in pixels
   * Default: 56px (Material-UI DataGrid header height)
   */
  headerHeight?: number;
  
  /**
   * Height reserved for pagination controls in pixels
   * Default: 52px (Material-UI pagination height)
   */
  paginationHeight?: number;
  
  /**
   * Additional height to reserve for other page elements (navbar, margins, etc.)
   * Default: 200px
   */
  reservedHeight?: number;
  
  /**
   * Minimum number of rows to show
   * Default: 5
   */
  minRows?: number;
  
  /**
   * Maximum number of rows to show
   * Default: 100
   */
  maxRows?: number;
}

export const useTablePageSize = (options: UseTablePageSizeOptions = {}) => {
  const {
    rowHeight = 52,
    headerHeight = 56,
    paginationHeight = 52,
    reservedHeight = 200,
    minRows = 5,
    maxRows = 100,
  } = options;

  const [pageSize, setPageSize] = useState(10);
  const [pageSizeOptions, setPageSizeOptions] = useState([5, 10, 25, 50]);

  useEffect(() => {
    const calculateOptimalPageSize = () => {
      const windowHeight = window.innerHeight;
      const availableHeight = windowHeight - reservedHeight - headerHeight - paginationHeight;
      
      // Calculate how many rows can fit in the available space
      const calculatedRows = Math.floor(availableHeight / rowHeight);
      
      // Ensure we stay within min/max bounds
      const optimalRows = Math.max(minRows, Math.min(maxRows, calculatedRows));
      
      // Create page size options as multiples of the optimal size
      const generateMultipleOptions = (baseSize: number): number[] => {
        const options: Set<number> = new Set();

        // Always include the base calculated size FIRST
        options.add(baseSize);

        // Add half size if it's >= minRows
        const halfSize = Math.floor(baseSize / 2);
        if (halfSize >= minRows) {
          options.add(halfSize);
        }

        // Add multiples (2x, 3x, etc.) up to maxRows
        for (let multiplier = 2; multiplier <= 4; multiplier++) {
          const multipleSize = baseSize * multiplier;
          if (multipleSize <= maxRows) {
            options.add(multipleSize);
          } else {
            break;
          }
        }

        // Always ensure we have at least 5 as minimum
        if (minRows <= 5) {
          options.add(5);
        }

        // Add common page size options if not included
        [10, 25, 50].forEach((size: number) => {
          if (size <= maxRows) {
            options.add(size);
          }
        });

        // Sort and return as array
        return Array.from(options).sort((a: number, b: number) => a - b);
      };

      const filteredOptions = generateMultipleOptions(optimalRows);

      // Set both at the same time to ensure they're in sync
      setPageSizeOptions(filteredOptions);
      setPageSize(optimalRows);
      
    };

    // Calculate initial page size
    calculateOptimalPageSize();

    // Recalculate on window resize
    const handleResize = () => {
      calculateOptimalPageSize();
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [rowHeight, headerHeight, paginationHeight, reservedHeight, minRows, maxRows]);

  return {
    pageSize,
    pageSizeOptions,
  };
};