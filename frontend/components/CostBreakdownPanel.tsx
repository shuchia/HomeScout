'use client';

import { useState } from 'react';
import { CostBreakdown } from '@/types/apartment';

interface CostBreakdownPanelProps {
  breakdown: CostBreakdown;
  pricingModel?: 'per_unit' | 'per_person' | null;
  bedrooms?: number;
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

export default function CostBreakdownPanel({ breakdown, pricingModel, bedrooms }: CostBreakdownPanelProps) {
  const { sources } = breakdown;
  const isScraped = (field: string) => sources.scraped.includes(field);
  const isIncluded = (utility: string) => sources.included.includes(utility);

  const isPerPerson = pricingModel === 'per_person';
  const defaultOccupancy = isPerPerson ? (bedrooms || 1) : 1;
  const [occupancy, setOccupancy] = useState(defaultOccupancy);
  const [includePet, setIncludePet] = useState(false);
  const [includeParking, setIncludeParking] = useState(false);
  const showOccupancy = occupancy > 1 || isPerPerson;

  // Shared costs: divided by occupancy (but NOT for per-person rent)
  const splitShared = (amount: number) =>
    occupancy > 1 ? Math.round(amount / occupancy) : amount;

  const perPersonSuffix = showOccupancy ? ' /person' : '';

  // Calculate per-person amounts
  const myRent = isPerPerson ? breakdown.base_rent : splitShared(breakdown.base_rent);
  // Pet rent and parking are optional — user must opt in
  const myPetRent = includePet ? breakdown.pet_rent : 0;
  const myParking = includeParking ? breakdown.parking_fee : 0;
  const myAmenity = splitShared(breakdown.amenity_fee);
  const myOtherMonthly = splitShared(breakdown.other_monthly_fees || 0);
  const myElectric = splitShared(breakdown.est_electric);
  const myGas = splitShared(breakdown.est_gas);
  const myWater = splitShared(breakdown.est_water);
  const myInternet = breakdown.est_internet; // personal (one connection)
  const myInsurance = breakdown.est_renters_insurance; // personal (per-person policy)
  const myLaundry = splitShared(breakdown.est_laundry);

  const monthlyTotal = myRent + myPetRent + myParking + myAmenity + myOtherMonthly
    + myElectric + myGas + myWater + myInternet + myInsurance + myLaundry;

  const myAdminFee = splitShared(breakdown.admin_fee || 0);
  const myDeposit = splitShared(breakdown.security_deposit);
  const moveInTotal = breakdown.application_fee + myAdminFee + myDeposit + monthlyTotal;

  const hasScrapedOneTimeFees =
    breakdown.application_fee > 0 || (breakdown.admin_fee || 0) > 0 || breakdown.security_deposit > 0;

  return (
    <div className="space-y-3 pt-2">
      {/* Monthly Costs */}
      <div className="space-y-0.5">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Monthly Costs</p>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">People:</span>
            <button
              onClick={() => setOccupancy(Math.max(1, occupancy - 1))}
              className="w-6 h-6 rounded-full border border-gray-300 text-gray-500 text-sm flex items-center justify-center hover:bg-gray-50"
            >
              -
            </button>
            <span className="text-sm font-medium w-4 text-center">{occupancy}</span>
            <button
              onClick={() => setOccupancy(Math.min(6, occupancy + 1))}
              className="w-6 h-6 rounded-full border border-gray-300 text-gray-500 text-sm flex items-center justify-center hover:bg-gray-50"
            >
              +
            </button>
          </div>
        </div>
        <LineItem label={`Base Rent${perPersonSuffix}`} amount={myRent} source="scraped" />
        {breakdown.pet_rent > 0 && (
          <label className="flex justify-between items-center text-sm py-1 cursor-pointer">
            <span className="text-gray-600 flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={includePet}
                onChange={(e) => setIncludePet(e.target.checked)}
                className="h-3.5 w-3.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              Pet Rent
              <span
                className={`inline-block w-1.5 h-1.5 rounded-full ${isScraped('pet_rent') ? 'bg-blue-500' : 'bg-gray-400'}`}
                title={isScraped('pet_rent') ? 'From listing' : 'Regional estimate'}
              />
            </span>
            <span className={includePet ? 'text-gray-900' : 'text-gray-400'}>{formatCost(breakdown.pet_rent)}</span>
          </label>
        )}
        {breakdown.parking_fee > 0 && (
          <label className="flex justify-between items-center text-sm py-1 cursor-pointer">
            <span className="text-gray-600 flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={includeParking}
                onChange={(e) => setIncludeParking(e.target.checked)}
                className="h-3.5 w-3.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              Parking
              <span
                className={`inline-block w-1.5 h-1.5 rounded-full ${isScraped('parking_fee') ? 'bg-blue-500' : 'bg-gray-400'}`}
                title={isScraped('parking_fee') ? 'From listing' : 'Regional estimate'}
              />
            </span>
            <span className={includeParking ? 'text-gray-900' : 'text-gray-400'}>{formatCost(breakdown.parking_fee)}</span>
          </label>
        )}
        {myAmenity > 0 && (
          <LineItem label={`Amenity Fee${perPersonSuffix}`} amount={myAmenity} source={isScraped('amenity_fee') ? 'scraped' : 'estimated'} />
        )}
        {myOtherMonthly > 0 && (
          <LineItem label={`Other Fees${perPersonSuffix}`} amount={myOtherMonthly} source={isScraped('other_monthly_fees') ? 'scraped' : 'estimated'} />
        )}

        <div className="border-t border-gray-100 my-1" />

        {isIncluded('electric') ? (
          <LineItem label="Electric" amount={0} source="included" />
        ) : (
          <LineItem label={`Electric${perPersonSuffix}`} amount={myElectric} source="estimated" />
        )}
        {isIncluded('heat') ? (
          <LineItem label="Heat/Gas" amount={0} source="included" />
        ) : (
          <LineItem label={`Heat/Gas${perPersonSuffix}`} amount={myGas} source="estimated" />
        )}
        {isIncluded('water') ? (
          <LineItem label="Water" amount={0} source="included" />
        ) : (
          <LineItem label={`Water${perPersonSuffix}`} amount={myWater} source="estimated" />
        )}
        {isIncluded('internet') ? (
          <LineItem label="Internet" amount={0} source="included" />
        ) : (
          <LineItem label="Internet" amount={myInternet} source="estimated" />
        )}
        {isIncluded('renters_insurance') ? (
          <LineItem label="Renter&apos;s Insurance" amount={0} source="included" />
        ) : (
          <LineItem label="Renter&apos;s Insurance" amount={myInsurance} source="estimated" />
        )}
        {isIncluded('laundry') ? (
          <LineItem label="Laundry" amount={0} source="included" />
        ) : (
          <LineItem label={`Laundry${perPersonSuffix}`} amount={myLaundry} source="estimated" />
        )}
      </div>

      <div className="flex justify-between items-center border-t border-gray-200 pt-2">
        <span className="font-semibold text-gray-900 text-sm">Est. Monthly Total{perPersonSuffix}</span>
        <span className="font-bold text-gray-900">{formatCost(monthlyTotal)}</span>
      </div>

      {/* Move-in Costs — always shown */}
      <div className="space-y-0.5 pt-2">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Move-in Costs</p>
        {breakdown.application_fee > 0 && (
          <LineItem label="Application Fee" amount={breakdown.application_fee} source={isScraped('application_fee') ? 'scraped' : 'estimated'} />
        )}
        {myAdminFee > 0 && (
          <LineItem label={`Admin Fee${perPersonSuffix}`} amount={myAdminFee} source={isScraped('admin_fee') ? 'scraped' : 'estimated'} />
        )}
        {myDeposit > 0 && (
          <LineItem label={`Security Deposit${perPersonSuffix}`} amount={myDeposit} source={isScraped('security_deposit') ? 'scraped' : 'estimated'} />
        )}
        {!hasScrapedOneTimeFees && (
          <p className="text-xs text-gray-400 italic py-1">No fees listed — check with property</p>
        )}
        <LineItem label={`First Month${perPersonSuffix}`} amount={monthlyTotal} source="estimated" />
        <div className="flex justify-between items-center border-t border-gray-200 pt-2">
          <span className="font-semibold text-gray-900 text-sm">Est. Move-in Total{perPersonSuffix}</span>
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
