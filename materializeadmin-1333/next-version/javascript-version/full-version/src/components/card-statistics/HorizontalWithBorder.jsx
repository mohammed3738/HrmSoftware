'use client'

// MUI Imports
import MuiCard from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Typography from '@mui/material/Typography'
import { styled } from '@mui/material/styles'

//Component Imports
import CustomAvatar from '@core/components/mui/Avatar'

const Card = styled(MuiCard)(({ color }) => ({
  transition: 'border 0.3s ease-in-out, box-shadow 0.3s ease-in-out, margin 0.3s ease-in-out',
  borderBottomWidth: '2px',
  borderBottomColor: `var(--mui-palette-${color}-darkerOpacity)`,
  '[data-skin="bordered"] &:hover': {
    boxShadow: 'none'
  },
  '&:hover': {
    borderBottomWidth: '3px',
    borderBottomColor: `var(--mui-palette-${color}-main) !important`,
    boxShadow: 'var(--mui-customShadows-xl)',
    marginBlockEnd: '-1px'
  }
}))

const HorizontalWithBorder = props => {
  // Props
  const { title, stats, trendNumber, avatarIcon, color } = props

  return (
    <Card color={color || 'primary'}>
      <CardContent className='flex flex-col gap-2'>
        <div className='flex items-center gap-4'>
          <CustomAvatar color={color} skin='light' variant='rounded'>
            <i className={avatarIcon} />
          </CustomAvatar>
          <Typography variant='h4'>{stats}</Typography>
        </div>
        <div className='flex flex-col'>
          <Typography color='text.primary'>{title}</Typography>
          <div className='flex items-center gap-2'>
            <Typography className='font-medium'>{`${trendNumber > 0 ? '+' : ''}${trendNumber}%`}</Typography>
            <Typography variant='body2' color='text.disabled'>
              than last week
            </Typography>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default HorizontalWithBorder
