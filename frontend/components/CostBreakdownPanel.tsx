'use client';

import { CostBreakdown } from '@/types/apartment';

interface CostBreakdownPanelProps {
  breakdown: CostBreakdown;
}

const formatCost = (amount: number): string => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(amount);
};

interface LineItemProps {
  label: string;
  amount: number;
  source: 'scraped' | 'estimated' | 'included';
}

function LineItem({ label, amount, source }: LineItemProps) {
  if (source === 'included') {
    return (
      <div className="flex justify-between items-center text-sm py-1">
        <span className="text-gray-600">{label}</span>
        <span className="text-green-600 font-medium">Included</span>
      </div>
    );
  }
  if (amount === 0) return null;
  return (
    <div className="flex justify-between items-center text-sm py-1">
      <span className="text-gray-600 flex items-center gap-1.5">
        {label}
        <span
          className={`inline-block w-1.5 h-1.5 rounded-full ${
            source === 'scraped' ? 'bg-blue-500' : 'bg-gray-400'
          }`}
          title={source === 'scraped' ? 'From listing' : 'Regional estimate'}
        />
      </span>
      <span className="text-gray-900">{formatCost(amount)}</span>
    </div>
  );
}

export default function CostBreakdownPanel({ breakdown }: CostBreakdownPanelProps) {
  const { sources } = breakdown;
  const isScraped = (field: string) => sources.scraped.includes(field);
  const isIncluded = (utility: string) => sources.included.includes(utility);

  const monthlyTotal =
    breakdown.base_rent +
    breakdown.pet_rent +
    breakdown.parking_fee +
    breakdown.amenity_fee +
    (breakdown.other_monthly_fees || 0) +
    breakdown.est_electric +
    breakdown.est_gas +
    breakdown.est_water +
    breakdown.est_internet +
    breakdown.est_renters_insurance +
    breakdown.est_laundry;

  const moveInTotal =
    breakdown.application_fee + (breakdown.admin_fee || 0) + breakdown.security_deposit + monthlyTotal;

  const hasScrapedOneTimeFees =
    breakdown.application_fee > 0 || (breakdown.admin_fee || 0) > 0 || breakdown.security_deposit > 0;

  return (
    <div className="space-y-3 pt-2">
      {/* Monthly Costs */}
      <div className="space-y-0.5">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Monthly Costs</p>
        <LineItem label="Base Rent" amount={breakdown.base_rent} source="scraped" />
        {breakdown.pet_rent > 0 && (
          <LineItem label="Pet Rent" amount={breakdown.pet_rent} source={isScraped('pet_rent') ? 'scraped' : 'estimated'} />
        )}
        {breakdown.parking_fee > 0 && (
          <LineItem label="Parking" amount={breakdown.parking_fee} source={isScraped('parking_fee') ? 'scraped' : 'estimated'} />
        )}
        {breakdown.amenity_fee > 0 && (
          <LineItem label="Amenity Fee" amount={breakdown.amenity_fee} source={isScraped('amenity_fee') ? 'scraped' : 'estimated'} />
        )}
        {(breakdown.other_monthly_fees || 0) > 0 && (
          <LineItem label="Other Fees" amount={breakdown.other_monthly_fees} source={isScraped('other_monthly_fees') ? 'scraped' : 'estimated'} />
        )}

        <div className="border-t border-gray-100 my-1" />

        {isIncluded('electric') ? (
          <LineItem label="Electric" amount={0} source="included" />
        ) : (
          <LineItem label="Electric" amount={breakdown.est_electric} source="estimated" />
        )}
        {isIncluded('heat') ? (
          <LineItem label="Heat/Gas" amount={0} source="included" />
        ) : (
          <LineItem label="Heat/Gas" amount={breakdown.est_gas} source="estimated" />
        )}
        {isIncluded('water') ? (
          <LineItem label="Water" amount={0} source="included" />
        ) : (
          <LineItem label="Water" amount={breakdown.est_water} source="estimated" />
        )}
        {isIncluded('internet') ? (
          <LineItem label="Internet" amount={0} source="included" />
        ) : (
          <LineItem label="Internet" amount={breakdown.est_internet} source="estimated" />
        )}
        {isIncluded('renters_insurance') ? (
          <LineItem label="Renter&apos;s Insurance" amount={0} source="included" />
        ) : (
          <LineItem label="Renter&apos;s Insurance" amount={breakdown.est_renters_insurance} source="estimated" />
        )}
        {isIncluded('laundry') ? (
          <LineItem label="Laundry" amount={0} source="included" />
        ) : (
          <LineItem label="Laundry" amount={breakdown.est_laundry} source="estimated" />
        )}
      </div>

      <div className="flex justify-between items-center border-t border-gray-200 pt-2">
        <span className="font-semibold text-gray-900 text-sm">Est. Monthly Total</span>
        <span className="font-bold text-gray-900">{formatCost(monthlyTotal)}</span>
      </div>

      {/* Move-in Costs — always shown */}
      <div className="space-y-0.5 pt-2">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Move-in Costs</p>
        {breakdown.application_fee > 0 && (
          <LineItem label="Application Fee" amount={breakdown.application_fee} source={isScraped('application_fee') ? 'scraped' : 'estimated'} />
        )}
        {(breakdown.admin_fee || 0) > 0 && (
          <LineItem label="Admin Fee" amount={breakdown.admin_fee} source={isScraped('admin_fee') ? 'scraped' : 'estimated'} />
        )}
        {breakdown.security_deposit > 0 && (
          <LineItem label="Security Deposit" amount={breakdown.security_deposit} source={isScraped('security_deposit') ? 'scraped' : 'estimated'} />
        )}
        {!hasScrapedOneTimeFees && (
          <p className="text-xs text-gray-400 italic py-1">No fees listed — check with property</p>
        )}
        <LineItem label="First Month" amount={monthlyTotal} source="estimated" />
        <div className="flex justify-between items-center border-t border-gray-200 pt-2">
          <span className="font-semibold text-gray-900 text-sm">Est. Move-in Total</span>
          <span className="font-bold text-gray-900">{formatCost(moveInTotal)}</span>
        </div>
      </div>

      <div className="flex gap-4 text-xs text-gray-400 pt-1">
        <span className="flex items-center gap-1">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500" />
          From listing
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-gray-400" />
          Regional estimate
        </span>
      </div>
    </div>
  );
}
