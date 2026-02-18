# HomeScout Frontend

A modern React frontend for the HomeScout AI-powered apartment finder, built with Next.js 14, TypeScript, and Tailwind CSS.

## Features

- **AI-Powered Search**: Find apartments ranked by match score using Claude AI
- **Interactive Image Carousels**: Browse apartment photos with smooth navigation
- **Responsive Design**: Works great on mobile, tablet, and desktop
- **Real-time Results**: See matches with scores, reasoning, and highlights

## Tech Stack

- **Framework**: Next.js 14 with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Carousel**: Embla Carousel React
- **API Client**: Native Fetch API

## Project Structure

```
frontend/
├── app/
│   ├── page.tsx           # Main home page with search and results
│   ├── layout.tsx         # Root layout with metadata
│   └── globals.css        # Global styles
├── components/
│   ├── SearchForm.tsx     # Search form with all inputs
│   ├── ApartmentCard.tsx  # Apartment display with match score
│   └── ImageCarousel.tsx  # Image carousel using Embla
├── lib/
│   └── api.ts             # API client for backend communication
├── types/
│   └── apartment.ts       # TypeScript interfaces
└── public/                # Static assets
```

## Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn
- Backend server running on port 8000

### Installation

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Create environment file:
   ```bash
   cp .env.example .env.local
   ```

4. Start the development server:
   ```bash
   npm run dev
   ```

5. Open [http://localhost:3000](http://localhost:3000) in your browser

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | `http://localhost:8000` |

## Components

### SearchForm
Handles user input for apartment search with:
- City selection
- Budget input
- Bedrooms/bathrooms dropdowns
- Property type checkboxes
- Move-in date picker
- Additional preferences textarea

### ApartmentCard
Displays apartment details including:
- Image carousel
- Match score badge (color-coded)
- Rent, beds, baths, sqft
- Amenities tags
- AI-generated reasoning
- Key highlights

### ImageCarousel
Touch-enabled image carousel with:
- Navigation arrows
- Pagination dots
- Swipe support
- Smooth transitions

## API Integration

The frontend communicates with the FastAPI backend through:

```typescript
// Search for apartments
const results = await searchApartments({
  city: "San Francisco, CA",
  budget: 3500,
  bedrooms: 2,
  bathrooms: 1,
  property_type: "Apartment, Condo",
  move_in_date: "2025-12-01",
  other_preferences: "Pet-friendly"
});
```

## Development

### Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run start` - Start production server
- `npm run lint` - Run ESLint

### Code Style

- TypeScript strict mode enabled
- ESLint for code quality
- Tailwind CSS for styling

## Troubleshooting

### "Unable to connect to server"
- Ensure the backend is running on port 8000
- Check that CORS is configured in the backend

### Images not loading
- Verify `next.config.ts` has the image domains configured
- Check browser console for specific errors

### TypeScript errors
- Run `npm run lint` to identify issues
- Ensure types match backend Pydantic models

## Learn More

- [Next.js Documentation](https://nextjs.org/docs)
- [Tailwind CSS Documentation](https://tailwindcss.com/docs)
- [Embla Carousel](https://www.embla-carousel.com/)

## License

MIT
