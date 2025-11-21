const snackbar = skin => ({
  MuiSnackbarContent: {
    styleOverrides: {
      root: ({ theme }) => ({
        borderRadius: 'var(--mui-shape-customBorderRadius-lg)',
        padding: theme.spacing(0, 4),
        ...(skin !== 'bordered'
          ? {
              boxShadow: 'var(--mui-customShadows-xs)'
            }
          : {
              boxShadow: 'none'
            }),
        '& .MuiSnackbarContent-message': {
          paddingBlock: theme.spacing(3)
        }
      })
    }
  }
})

export default snackbar
